"""Deploy the tested commit image using a Railway project token (no CLI)."""

import json
import os
import re
import sys
import time
from urllib.parse import urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ENDPOINT = "https://backboard.railway.com/graphql/v2"


class RailwayError(RuntimeError):
    pass


def graphql(token, query, variables=None):
    request = Request(
        ENDPOINT,
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Content-Type": "application/json", "Project-Access-Token": token},
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except HTTPError as error:
        raise RailwayError(f"Railway HTTP {error.code}; check permissions and limits.") from None
    except URLError:
        raise RailwayError("Could not connect to Railway; deployment was not confirmed.") from None
    if payload.get("errors"):
        # Railway errors contain no credentials; expose only a compact diagnostic
        # so a failed GitHub job can be fixed without downloading private logs.
        error = payload["errors"][0]
        extensions = error.get("extensions") or {}
        code = str(extensions.get("code", "UNKNOWN"))
        message = str(error.get("message", "request rejected"))
        if re.search(r"token|password|secret|sensitive", message, flags=re.IGNORECASE):
            message = "request rejected"
        raise RailwayError(f"Railway GraphQL {code}: {message[:240]}")
    if not isinstance(payload.get("data"), dict):
        raise RailwayError("Railway returned an invalid response.")
    return payload["data"]


def wait_for_deployment(api, deployment_id, timeout=900, interval=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = api(
            "query($id: String!) { deployment(id: $id) { id status } }",
            {"id": deployment_id},
        )
        deployment = data.get("deployment")
        if not deployment or deployment["id"] != deployment_id:
            raise RailwayError("Railway did not return the requested deployment.")
        status = deployment["status"]
        print(f"Deployment {deployment_id}: {status}", flush=True)
        if status == "SUCCESS":
            return
        if status in {"FAILED", "CRASHED", "REMOVED", "SKIPPED", "CANCELED", "COMPLETED"}:
            raise RailwayError(f"Deployment failed with status {status}.")
        time.sleep(interval)
    raise RailwayError("Timed out waiting for the new Railway deployment.")


def find_service_id(api, scope, public_url):
    hostname = urlparse(public_url).hostname
    if not hostname:
        raise RailwayError("RAILWAY_BASE_URL must be an HTTPS URL.")
    data = api(
        """query($id: String!, $projectId: String!) {
          environment(id: $id, projectId: $projectId) {
            serviceInstances(first: 100) {
              edges { node { serviceId serviceName domains { serviceDomains { domain } } } }
            }
          }
        }""",
        {"id": scope["environmentId"], "projectId": scope["projectId"]},
    )
    instances = data.get("environment", {}).get("serviceInstances", {}).get("edges", [])
    matches = []
    for edge in instances:
        instance = edge.get("node", {})
        domains = instance.get("domains", {}).get("serviceDomains", [])
        if any(domain.get("domain") == hostname for domain in domains):
            matches.append(instance.get("serviceId"))
    if len(matches) != 1 or not matches[0]:
        raise RailwayError("Could not identify exactly one API service from RAILWAY_BASE_URL.")
    return matches[0]


def deploy(environ=None, api=None):
    environ = os.environ if environ is None else environ
    required = ("RAILWAY_TOKEN", "RAILWAY_BASE_URL", "GITHUB_REPOSITORY", "GITHUB_SHA")
    missing = [key for key in required if not environ.get(key)]
    if missing:
        raise RailwayError("Missing configuration: " + ", ".join(missing))
    sha = environ["GITHUB_SHA"]
    repository = environ["GITHUB_REPOSITORY"].lower()
    if not re.fullmatch(r"[a-fA-F0-9]{40}", sha):
        raise RailwayError("GITHUB_SHA must be a complete commit SHA.")
    if not re.fullmatch(r"[a-z0-9_.-]+/[a-z0-9_.-]+", repository):
        raise RailwayError("Invalid GITHUB_REPOSITORY.")
    if api is None:
        api = lambda query, variables=None: graphql(environ["RAILWAY_TOKEN"], query, variables)

    scope = api("query { projectToken { projectId environmentId } }")["projectToken"]
    service_id = environ.get("RAILWAY_SERVICE_ID") or find_service_id(
        api, scope, environ["RAILWAY_BASE_URL"]
    )
    service = api(
        "query($id: String!) { service(id: $id) { id projectId } }",
        {"id": service_id},
    )["service"]
    if service["projectId"] != scope["projectId"]:
        raise RailwayError("The service does not belong to the token's project.")

    image = f"ghcr.io/{repository}:{sha}"
    variables = {"serviceId": service_id, "environmentId": scope["environmentId"]}
    result = api(
        """mutation($serviceId: String!, $environmentId: String!,
                    $input: ServiceInstanceUpdateInput!) {
          serviceInstanceUpdate(serviceId: $serviceId,
            environmentId: $environmentId, input: $input)
        }""",
        {**variables, "input": {"source": {"image": image},
                                "healthcheckPath": "/api/v1/persons",
                                "healthcheckTimeout": 120}},
    )
    if not result.get("serviceInstanceUpdate"):
        raise RailwayError("Railway did not accept the image update.")
    result = api(
        """mutation($serviceId: String!, $environmentId: String!) {
          serviceInstanceDeployV2(serviceId: $serviceId, environmentId: $environmentId)
        }""",
        variables,
    )
    deployment_id = result.get("serviceInstanceDeployV2")
    if not isinstance(deployment_id, str) or not deployment_id:
        raise RailwayError("Railway did not return a deployment ID.")
    print(f"Deploying {image}", flush=True)
    wait_for_deployment(api, deployment_id)
    print("Railway deployment succeeded.", flush=True)
    return deployment_id


if __name__ == "__main__":
    try:
        deploy()
    except (RailwayError, KeyError, ValueError, TimeoutError) as error:
        print(f"::error title=Railway deployment::{error}", flush=True)
        print(f"Deployment stopped: {error}", file=sys.stderr)
        sys.exit(1)
