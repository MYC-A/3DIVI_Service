from collections import Counter
import base64
import json
import os
import time
import pytest

def test_loading_images(client):
    test_image_bytes = b'test_image_dlya_proverochki'
    base64_image = base64.b64encode(test_image_bytes).decode('utf-8')

    payload_images = [{
        "base64": base64_image,
        "filename": "awesome_filename.png"
    }]

    payload = {
        "task_id": None,
        "images": payload_images
    }


    response = client.post("/upload_images_base64", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data.get("message") == "Images uploaded successfully"
    task_id = data.get("task_id")
    assert task_id is not None


@pytest.mark.slow
def test_process_images(client, pytestconfig):
    # Получаем путь к JSON и номер теста из опций командной строки
    clusters_json_path = pytestconfig.getoption("clusters_json")
    test_number = pytestconfig.getoption("test_number")

    # Загружаем ожидаемые кластеры (формат: список списков имен файлов)
    with open(clusters_json_path, "r", encoding="utf-8") as f:
        expected_clusters = json.load(f)

    # Определяем папку с изображениями: /test/images/test_[номер теста]
    images_folder = os.path.join(os.path.dirname(__file__), "images", f"test_{test_number}")

    # Для каждого файла из ожидаемого JSON читаем его содержимое и кодируем в base64
    payload_images = []
    for cluster in expected_clusters:
        for filename in cluster:
            filepath = os.path.join(images_folder, filename)
            with open(filepath, "rb") as f:
                file_bytes = f.read()
            encoded = base64.b64encode(file_bytes).decode("utf-8")
            payload_images.append({
                "base64": encoded,
                "filename": filename
            })

    payload = {
        "task_id": None,
        "images": payload_images
    }

    response = client.post("/upload_images_base64", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data.get("message") == "Images uploaded successfully"
    task_id = data.get("task_id")
    assert task_id is not None

    response = client.post("/process_images", params={"task_id": task_id})
    assert response.status_code == 200, response.text
    data = response.json()
    expected_message = f"Processing task started for task_id: {task_id}"
    assert data.get("message") == expected_message

    timeout = 600
    interval = 20
    elapsed = 0

    while elapsed < timeout:

        response = client.get("/get_clusters_by_task_id", params={"task_id": task_id})
        assert response.status_code == 200, response.text
        clusters_data = response.json()
        actual_clusters = {}
        clusters_list = clusters_data.get('clusters')

        if len(clusters_list) != 0:

            for cluster_data in clusters_list:
                cluster = cluster_data[2]
                image_path = cluster_data[1]
                if cluster in actual_clusters.keys():
                    actual_clusters[cluster].append(image_path)
                else:
                    actual_clusters[cluster] = [image_path]

            break

        time.sleep(interval)
        elapsed += interval
    else:
        pytest.fail("Timeout waiting for image processing to complete")

    # сравниваем количество-численность кластеров
    expected = Counter([len(i) for i in expected_clusters])
    actual = Counter([len(i) for i in actual_clusters.values()])

    assert actual == expected, f"Expected {expected}, got {actual}"
