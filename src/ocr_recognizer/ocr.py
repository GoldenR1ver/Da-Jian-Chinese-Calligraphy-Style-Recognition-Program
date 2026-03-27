import requests
import base64
import json


def get_access_token(api_key, secret_key):
    url = "https://aip.baidubce.com/oauth/2.0/token"
    params = {"grant_type": "client_credentials", "client_id": api_key, "client_secret": secret_key}
    return str(requests.post(url, params=params).json().get("access_token"))

def image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def ocr_recognize(image_path, api_key, secret_key):
    access_token = get_access_token(api_key, secret_key)
    
    url = f"https://aip.baidubce.com/rest/2.0/ocr/v1/accurate?access_token={access_token}"

    image_base64 = image_to_base64(image_path)

    params = {
        "image": image_base64,
        "recognize_granularity": "small",  # 定位单字符位置
        "vertexes_location": "true",       # 返回文字外接多边形顶点位置
        "detect_direction": "true",        # 检测图像朝向
        "probability": "true",             # 返回每一行的置信度
        "paragraph": "true"                # 输出段落信息
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}

    response = requests.post(url, data=params, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        return {"error": "请求失败", "status_code": response.status_code}

def parse_ocr_result(result):
    """
    解析 OCR 结果，返回每行的文字及每个字符的位置
    :param result: OCR 识别结果
    :return: 每行的文字及字符位置信息
    """
    parsed_result = []
    
    # 检查是否有识别结果
    if "words_result" in result:
        for line in result['words_result']:
            line_text = line['words']  # 每行的文字
            line_location = line['location']  # 该行文字的位置信息
            line_chars = []  # 用于存储每行的字符及位置
            
            for char in line['chars']:
                char_text = char['char']  # 字符本身
                char_location = char['location']  # 字符的位置信息
                line_chars.append({
                    "char": char_text,
                    "location": char_location
                })
            
            # 将当前行的文字和字符位置信息存入解析结果
            parsed_result.append({
                "line_text": line_text,
                "line_location": line_location,
                "chars": line_chars
            })
    
    return parsed_result



if __name__ == "__main__":
    import os
    import argparse

    parser = argparse.ArgumentParser(description="OCR recognize a handwriting image via Baidu OCR.")
    parser.add_argument("image_path", help="Path to input image")
    parser.add_argument("--api-key", default=os.getenv("BAIDU_OCR_API_KEY"), help="Baidu OCR API key (or env BAIDU_OCR_API_KEY)")
    parser.add_argument("--secret-key", default=os.getenv("BAIDU_OCR_SECRET_KEY"), help="Baidu OCR secret key (or env BAIDU_OCR_SECRET_KEY)")
    args = parser.parse_args()

    if not args.api_key or not args.secret_key:
        raise SystemExit(
            "Missing credentials. Provide --api-key/--secret-key or set "
            "BAIDU_OCR_API_KEY and BAIDU_OCR_SECRET_KEY."
        )

    result = ocr_recognize(args.image_path, args.api_key, args.secret_key)
    parsed_result = parse_ocr_result(result)
    print(json.dumps(parsed_result, ensure_ascii=False, indent=2))
