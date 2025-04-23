import requests
import base64
import json
import os

# --- Configuration ---
# Make sure this path is correct relative to where you run the script,
# or provide an absolute path.
IMAGE_PATH = "examples/_images/dogs.jpg"
API_ENDPOINT = "http://localhost:11368/api/generate"

# Define the model name (use one supported by the API)
# Based on the code, 'efficientsam' should resolve to 'efficientsam:latest'
MODEL_NAME = "efficientsam"

# Define the prompt (optional, but included in your Python example)
# Ensure coordinates are relevant to the image size if using them.
# For dogs.jpg (seems to be 1920x1280), the example points are valid.
PROMPT = {
    "points": [[1439, 504], [1439, 1289]],
    "point_labels": [1, 1] # 1 indicates foreground points
}

# --- Script Logic ---

def send_image_to_api(image_path: str, endpoint_url: str, model: str, prompt: dict = None):
    """
    Reads an image, encodes it to Base64, and sends it to the specified API endpoint.

    Args:
        image_path: Path to the image file.
        endpoint_url: The URL of the API endpoint.
        model: The name of the model to use.
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
    # Add the prompt to the payload if it was provided
    if prompt:
        payload["prompt"] = prompt

    # 4. Define headers
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json" # Specify we expect JSON back
    }

    # 5. Send the POST request
    print(f"Sending request to {endpoint_url} with model '{model}'...")
    try:
        response = requests.post(endpoint_url, headers=headers, json=payload)

        # 6. Check the response status and handle the result
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)

        print("Request successful!")
        try:
            response_data = response.json()
            print("Response JSON:", response_data.keys())

            # Save the full JSON response to a file
            output_json_path = "response_output.json"
            try:
                with open(output_json_path, 'w') as f:
                    json.dump(response_data, f, indent=2)
                print(f"Successfully saved full JSON response to '{output_json_path}'")
            except Exception as e:
                print(f"Error saving JSON to file: {e}")

            # Optional: Try to decode and save the mask if returned like the curl example
            # (Assuming the API returns a base64 encoded mask in a 'mask' field directly,
            # based on the curl example `jq -r .mask | base64 --decode`)
            # Note: The Python types suggest the mask is in `annotations`,
            # the API might differ in practice or follow the curl example.
            if 'annotations' in response_data and isinstance(response_data['annotations'], list) and response_data['annotations']:
                 # Try accessing the mask from the first annotation
                 first_annotation = response_data['annotations'][0]
                 if 'mask' in first_annotation and isinstance(first_annotation['mask'], str):
                     try:
                         mask_b64 = first_annotation['mask']
                         mask_bytes = base64.b64decode(mask_b64)
                         output_mask_path = "mask_from_api.png"
                         with open(output_mask_path, "wb") as f:
                             f.write(mask_bytes)
                         print(f"Successfully decoded and saved mask to '{output_mask_path}'")
                     except Exception as decode_err:
                         print(f"Could not decode or save mask from annotation: {decode_err}")
                 else:
                     print("Mask data not found in the expected format within the first annotation.")

            # Fallback check if 'mask' is directly in the root like curl example suggests
            elif 'mask' in response_data and isinstance(response_data['mask'], str):
                try:
                    mask_b64 = response_data['mask']
                    mask_bytes = base64.b64decode(mask_b64)
                    output_mask_path = "mask_from_api.png"
                    with open(output_mask_path, "wb") as f:
                        f.write(mask_bytes)
                    print(f"Successfully decoded and saved mask from root 'mask' field to '{output_mask_path}'")
                except Exception as decode_err:
                    print(f"Could not decode or save mask from root 'mask' field: {decode_err}")
            else:
                 print("Mask data not found in response annotations or as a root 'mask' field.")


        except json.JSONDecodeError:
            print("Error: Could not decode JSON response.")
            print("Response Text:", response.text)

    except requests.exceptions.RequestException as e:
        print(f"Error sending request: {e}")
        # If the response object exists, print more details
        if e.response is not None:
            print(f"Response Status Code: {e.response.status_code}")
            print(f"Response Text: {e.response.text}")


# --- Run the function ---
if __name__ == "__main__":
    send_image_to_api(
        image_path=IMAGE_PATH,
        endpoint_url=API_ENDPOINT,
        model=MODEL_NAME,
        prompt=PROMPT # Pass the prompt dictionary
    )