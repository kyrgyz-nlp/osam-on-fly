import requests
import base64
import json
import os
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

# Make sure this path is correct relative to where you run the script,
# or provide an absolute path.
IMAGE_PATH = "examples/_images/dogs.jpg"
# Update this to your deployed app URL without the port (e.g., https://your-osam-app-name.fly.dev/api/generate)
# Or keep it as http://localhost:11368/api/generate for local testing
API_ENDPOINT = "http://localhost:11368/api/generate"

# Define the model name (use one supported by the API)
# Consult the README https://github.com/wkentaro/osam for supported models
MODEL_NAME = "efficientsam"

# Define the prompt (optional, but included in your Python example)
# Ensure coordinates are relevant to the image size if using them.
# For dogs.jpg (seems to be 1920x1280), the example points are valid.
PROMPT = {
    "points": [[1439, 504], [1439, 1289]],
    "point_labels": [1, 1] # 1 indicates foreground points
}

# Get the API key from environment variable
API_KEY = os.environ.get("API_KEY")
if not API_KEY and "development" not in os.environ.get("APP_ENV", "").lower():
    # If API_KEY is not set and not explicitly in development mode, raise an error.
    # Note: The server decides enforcement, this is a client-side check for convenience.
    raise ValueError("`API_KEY` environment variable not set. Please set it to your secret key.")
elif not API_KEY and "development" in os.environ.get("APP_ENV", "").lower():
    print("Warning: `API_KEY` environment variable not set. Running in development mode, authentication might be bypassed on the server.")


def send_image_to_api(image_path: str, endpoint_url: str, model: str, api_key: str, prompt: dict = None):
    """
    Reads an image, encodes it to Base64, and sends it to the specified API endpoint
    with API key authentication.

    Args:
        image_path: Path to the image file.
        endpoint_url: The URL of the API endpoint.
        model: The name of the model to use.
        api_key: The API key for authentication.
        prompt: An optional dictionary representing the prompt (points, labels, etc.).
    """
    # 1. Check if the image file exists
    if not os.path.exists(image_path):
        print(f"Error: Image file not found at '{image_path}'")
        return

    # 2. Read image file in binary mode and encode to Base64
    try:
        with open(image_path, "rb") as image_file:
            image_bytes = image_file.read()
            # Encode bytes to Base64 bytes, then decode to UTF-8 string for JSON
            base64_encoded_image = base64.b64encode(image_bytes).decode('utf-8')
        print(f"Successfully read and encoded '{image_path}'")
    except Exception as e:
        print(f"Error reading or encoding file: {e}")
        return

    # 3. Construct the request payload (JSON body)
    payload = {
        "model": model,
        "image": base64_encoded_image,
    }
    if prompt:
        payload["prompt"] = prompt

    # 4. Define headers, including the API Key
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-API-Key": api_key
    }

    # 5. Send the POST request
    print(f"Sending request to {endpoint_url} with model '{model}'...")
    try:
        response = requests.post(endpoint_url, headers=headers, json=payload)

        # 6. Check the response status and handle the result
        if response.status_code == 200:
            print("Request successful!")
            try:
                response_data = response.json()
                print("Response JSON keys:", response_data.keys())

                output_json_path = "response_output.json"
                try:
                    with open(output_json_path, 'w') as f:
                        json.dump(response_data, f, indent=2)
                    print(f"Successfully saved full JSON response to '{output_json_path}'")
                except Exception as e:
                    print(f"Error saving JSON to file: {e}")

                # Optional: Try to decode and save the mask if returned
                # (Checking both 'annotations' structure and direct 'mask' field)
                mask_saved = False
                if 'annotations' in response_data and isinstance(response_data['annotations'], list) and response_data['annotations']:
                    first_annotation = response_data['annotations'][0]
                    if 'mask' in first_annotation and isinstance(first_annotation['mask'], str):
                        try:
                            mask_b64 = first_annotation['mask']
                            mask_bytes = base64.b64decode(mask_b64)
                            output_mask_path = "mask_from_api.png"
                            with open(output_mask_path, "wb") as f:
                                f.write(mask_bytes)
                            print(f"Successfully decoded and saved mask from annotation to '{output_mask_path}'")
                            mask_saved = True
                        except Exception as decode_err:
                            print(f"Could not decode or save mask from annotation: {decode_err}")
                    else:
                        print("Mask data not found in the expected format within the first annotation.")

                # Fallback check if 'mask' is directly in the root
                if not mask_saved and 'mask' in response_data and isinstance(response_data['mask'], str):
                    try:
                        mask_b64 = response_data['mask']
                        mask_bytes = base64.b64decode(mask_b64)
                        output_mask_path = "mask_from_api.png"
                        with open(output_mask_path, "wb") as f:
                            f.write(mask_bytes)
                        print(f"Successfully decoded and saved mask from root 'mask' field to '{output_mask_path}'")
                        mask_saved = True
                    except Exception as decode_err:
                        print(f"Could not decode or save mask from root 'mask' field: {decode_err}")

                if not mask_saved:
                    print("Mask data not found in response annotations or as a root 'mask' field.")

            except json.JSONDecodeError:
                print("Error: Could not decode JSON response.")
                print("Response Text:", response.text)

        elif response.status_code == 403:
            print(f"Authentication Error ({response.status_code}): Forbidden.")
            try:
                 print("Server Response:", response.json())
            except json.JSONDecodeError:
                 print("Server Response:", response.text)
            print("Ensure the correct API key is set in the API_KEY environment variable and matches the server's configured key.")
        elif response.status_code == 422:
             print(f"Validation Error ({response.status_code}): Check your request payload.")
             try:
                 print("Server Response:", response.json())
             except json.JSONDecodeError:
                 print("Server Response:", response.text)
        elif response.status_code >= 500:
            print(f"Server Error ({response.status_code}): An error occurred on the server.")
            print("Server Response:", response.text)
            print("Check server logs (e.g., `fly logs -a <your-app-name>`) for more details.")
        else:
            print(f"Error: Received status code {response.status_code}")
            print("Response Text:", response.text)
            response.raise_for_status() # Raise an HTTPError for other bad responses (e.g., 4xx)

    except requests.exceptions.RequestException as e:
        print(f"Error sending request: {e}")
        if e.response is not None:
            print(f"Response Status Code: {e.response.status_code}")
            print(f"Response Text: {e.response.text}")


if __name__ == "__main__":
    # Only proceed if API_KEY is set or explicitly in development mode
    if API_KEY or "development" in os.environ.get("APP_ENV", "").lower():
        send_image_to_api(
            image_path=IMAGE_PATH,
            endpoint_url=API_ENDPOINT,
            model=MODEL_NAME,
            api_key=API_KEY if API_KEY else "dummy_key_for_dev",
            prompt=PROMPT
        )
    else:
        # This case is already handled by the check at the start, but kept for clarity
        print("Execution stopped because API_KEY is not set and not in development mode.")