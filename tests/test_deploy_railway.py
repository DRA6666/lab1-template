import io
from unittest.mock import Mock

import pytest

from scripts.deploy_railway import RailwayError, deploy, graphql, wait_for_deployment


def config():
    return {"RAILWAY_TOKEN": "test-token", "RAILWAY_SERVICE_ID": "api-service",
            "RAILWAY_BASE_URL": "https://person-api.up.railway.app",
            "GITHUB_REPOSITORY": "DRA6666/lab1-template", "GITHUB_SHA": "a" * 40}


def test_missing_credentials_prevent_any_api_call():
    api = Mock()
    with pytest.raises(RailwayError, match="Missing configuration"):
        deploy({}, api)
    api.assert_not_called()


def test_service_is_found_from_its_public_domain_when_id_is_not_configured():
    data = config()
    data.pop("RAILWAY_SERVICE_ID")
    api = Mock(side_effect=[
        {"projectToken": {"projectId": "project", "environmentId": "production"}},
        {"environment": {"serviceInstances": {"edges": [
            {"node": {"serviceId": "postgres", "serviceName": "Postgres",
                      "domains": {"serviceDomains": []}}},
            {"node": {"serviceId": "api-service", "serviceName": "api",
                      "domains": {"serviceDomains": [{"domain": "person-api.up.railway.app"}]}}},
        ]}}},
        {"service": {"id": "api-service", "projectId": "project"}},
        {"serviceInstanceUpdate": True},
        {"serviceInstanceDeployV2": "new-deployment"},
        {"deployment": {"id": "new-deployment", "status": "SUCCESS"}},
    ])
    assert deploy(data, api) == "new-deployment"
    assert api.call_args_list[1].args[1] == {"id": "production", "projectId": "project"}


def test_ambiguous_public_domain_prevents_deployment():
    data = config()
    data.pop("RAILWAY_SERVICE_ID")
    api = Mock(side_effect=[
        {"projectToken": {"projectId": "project", "environmentId": "production"}},
        {"environment": {"serviceInstances": {"edges": []}}},
    ])
    with pytest.raises(RailwayError, match="exactly one"):
        deploy(data, api)
    assert api.call_count == 2


def test_deploy_uses_commit_image_and_waits_for_its_deployment():
    api = Mock(side_effect=[
        {"projectToken": {"projectId": "project", "environmentId": "production"}},
        {"service": {"id": "api-service", "projectId": "project"}},
        {"serviceInstanceUpdate": True},
        {"serviceInstanceDeployV2": "new-deployment"},
        {"deployment": {"id": "new-deployment", "status": "SUCCESS"}},
    ])
    assert deploy(config(), api) == "new-deployment"
    update = api.call_args_list[2].args[1]
    assert update["input"]["source"]["image"] == "ghcr.io/dra6666/lab1-template:" + "a" * 40
    assert update["environmentId"] == "production"
    assert api.call_args_list[4].args[1] == {"id": "new-deployment"}


def test_wrong_project_prevents_mutations():
    api = Mock(side_effect=[
        {"projectToken": {"projectId": "project", "environmentId": "production"}},
        {"service": {"id": "api-service", "projectId": "different-project"}},
    ])
    with pytest.raises(RailwayError, match="does not belong"):
        deploy(config(), api)
    assert api.call_count == 2


def test_failed_deployment_stops_pipeline():
    api = Mock(return_value={"deployment": {"id": "new", "status": "CRASHED"}})
    with pytest.raises(RailwayError, match="CRASHED"):
        wait_for_deployment(api, "new")


def test_queued_deployment_is_polled_until_success(monkeypatch):
    monkeypatch.setattr("scripts.deploy_railway.time.sleep", lambda _: None)
    api = Mock(side_effect=[
        {"deployment": {"id": "new", "status": "DEPLOYING"}},
        {"deployment": {"id": "new", "status": "SUCCESS"}},
    ])
    wait_for_deployment(api, "new")
    assert api.call_count == 2


def test_timeout_is_not_reported_as_success():
    with pytest.raises(RailwayError, match="Timed out"):
        wait_for_deployment(Mock(), "new", timeout=0)


def test_graphql_errors_fail_even_with_http_200(monkeypatch):
    response = io.BytesIO(b'{"errors":[{"message":"sensitive data"}]}')
    monkeypatch.setattr("scripts.deploy_railway.urlopen", lambda *args, **kwargs: response)
    with pytest.raises(RailwayError) as error:
        graphql("test-token", "query { projectToken { projectId } }")
    assert "sensitive data" not in str(error.value)
