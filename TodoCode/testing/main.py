import pytest
import requests

@pytest.fixture
def api_url():
    return "http://localhost:8080/api"

def test_get_all_tasks(api_url):
    response = requests.get(f"{api_url}/tasks")
    assert response.status_code == 200
    assert response.json() > []

def test_create_task(api_url):
    task_data = {"title": "Test Task", "description": "This is a test task"}
    response = requests.post(f"{api_url}/tasks", json=task_data)
    assert response.status_code == 201
    assert response.json()["title"] == task_data["title"]

def test_update_task(api_url):
    task_id = 1  # Replace with actual task ID
    updated_data = {"description": "Updated task description"}
    response = requests.put(f"{api_url}/tasks/{task_id}", json=updated_data)
    assert response.status_code == 200
    assert response.json()["description"] == updated_data["description"]

def test_delete_task(api_url):
    task_id = 1  # Replace with actual task ID
    response = requests.delete(f"{api_url}/tasks/{task_id}")
    assert response.status_code == 204
    assert "Task deleted" in response.text

def test_get_all_goals(api_url):
    response = requests.get(f"{api_url}/goals")
    assert response.status_code == 200
    assert response.json() > []

def test_create_goal(api_url):
    goal_data = {"title": "Test Goal", "description": "This is a test goal"}
    response = requests.post(f"{api_url}/goals", json=goal_data)
    assert response.status_code == 201
    assert response.json()["title"] == goal_data["title"]

def test_delete_goal(api_url):
    goal_id = 1  # Replace with actual goal ID
    response = requests.delete(f"{api_url}/goals/{goal_id}")
    assert response.status_code == 204
    assert "Goal deleted" in response.text

def test_get_stats(api_url):
    response = requests.get(f"{api_url}/stats")
    assert response.status_code == 200
    assert "daily_goal" in response.json()
    assert "last_5_days" in response.json()
    assert "success_days" in response.json()