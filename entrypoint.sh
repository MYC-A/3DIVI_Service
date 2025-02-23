#!/bin/bash
if [ -d "/3DiViFaceSDK/3_24_2/python_api" ]; then
    echo "Installing face_sdk_3divi from mounted volume..."
    pip install --no-cache-dir "face_sdk_3divi @ file:///3DiViFaceSDK/3_24_2/python_api"
else
    echo "Warning: /3DiViFaceSDK/3_24_2/python_api not found!"
fi

exec "$@"
