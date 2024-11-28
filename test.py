import base64
import requests
import dotenv
import os

dotenv.load_dotenv()

image_api_url = os.getenv("image_api_detection_url")

def test_detection_api(image_path: str, api_url: str = image_api_url):
    """
    Тестирует обращение к API детекции изображения.

    :param image_path: Путь к изображению для загрузки.
    :param api_url: URL конечной точки API.
    """
    try:
        # Чтение изображения и преобразование в base64
        with open(image_path, "rb") as image_file:
            encoded_image = base64.b64encode(image_file.read()).decode("utf-8")

        # Формирование данных запроса
        payload = {
            "_image": {
                "blob": encoded_image,
                "format": "IMAGE"
            },
            "objects": [{}]
        }

        # Отправка POST-запроса
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"  # Указывается в примере Swagger
        }
        response = requests.post(api_url, json=payload, headers=headers)

        # Проверка статуса и вывод результата
        print(f"HTTP Status Code: {response.status_code}")
        if response.status_code == 200:
            print("Response JSON:")
            print(response.json())
        else:
            print("Error Response:")
            print(response.text)

    except Exception as e:
        print(f"Ошибка при обработке: {e}")


# Пример вызова функции
if __name__ == "__main__":
    image_path = "/home/lichniy/Downloads/3divi_dataset/small_dataset/eeddae4f-bb70-4cd8-9203-b806758752a4.jpg"
    test_detection_api(image_path)
