import os
import csv
import time
import ast
import json
import textwrap
import pandas as pd
from urllib.parse import quote
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import re
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def extract_expenses_from_text(university_name, visible_text):
    system_prompt = (
        "You are a university cost extraction agent. Return a JSON list of estimated annual total costs of attendance for the most recent academic year.\n"
        "Prioritize rows labeled 'Total Expenses (In-State)', 'Total Expenses (Out-of-State)', 'Cost of Attendance (In-State)', or similar.\n"
        "If such rows are missing, calculate totals from tuition, fees, housing, food/meals, books, and personal expenses.\n"
        "Response format (JSON list):\n"
        "[\n"
        "  {\"label\": \"Average Annual Cost (In-State)\", \"value\": \"$10,024\", \"year\": \"2024–2025\"},\n"
        "  {\"label\": \"Average Annual Cost (Out-of-State)\", \"value\": \"$18,634\", \"year\": \"2024–2025\"}\n"
        "]"
    )

    chunks = textwrap.wrap(visible_text, width=3000, break_long_words=False, replace_whitespace=False)
    messages = [{"role": "system", "content": system_prompt}]

    for chunk in chunks[:-1]:
        messages.append({"role": "user", "content": f"(Partial chunk from {university_name}):\n{chunk}"})
    messages.append({"role": "user", "content": f"(Final chunk from {university_name}):\n{chunks[-1]}"})

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=messages,
            temperature=0,
            max_tokens=2048,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"[GPT ERROR]: {str(e)}"

def get_visible_expense_text(driver):
    time.sleep(2)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    for div in soup.find_all("div"):
        text = div.get_text(separator="\n").strip()
        if "Estimated expenses for academic year" in text or "Net Price" in text:
            return text
    raise Exception("Could not find Estimated Expenses section")

def click_tuition_tab(driver):
    try:
        WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "Tuition"))).click()
        print(" Clicked Tuition tab")
        return True
    except:
        print(" Tuition tab not found by direct text, using fallback...")
        for link in driver.find_elements(By.TAG_NAME, "a"):
            link_text = link.text.strip().replace('\xa0', ' ').lower()
            if "tuition" in link_text and ("fee" in link_text or "estimate" in link_text):
                try:
                    driver.execute_script("arguments[0].scrollIntoView(true);", link)
                    time.sleep(0.5)
                    link.click()
                    print(f"Fallback clicked: {link.text}")
                    return True
                except:
                    continue
    return False

def extract_json_or_bullet_points(raw, university):
    cleaned = re.sub(r"```(json)?", "", raw).strip()
    match = re.search(r"\[.*?\]", cleaned, re.DOTALL)
    if match:
        json_str = match.group(0)
        try:
            return json.loads(json_str)
        except:
            try:
                return ast.literal_eval(json_str)
            except:
                pass

    bullet_lines = re.findall(r"- \*\*(.*?)\*\*: \$?([\d,]+)", raw)
    results = []
    for label, amount in bullet_lines:
        results.append({
            "label": label.strip(),
            "value": f"${amount}",
            "year": "2024–2025"
        })
    if results:
        return results

    raise ValueError("No JSON or parsable bullet points found in GPT output")

def process_university(university_name):
    url = f"https://nces.ed.gov/collegenavigator/?q={quote(university_name)}"
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=options)

    try:
        driver.get(url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".resultsTable a"))).click()
        print(" Clicked university")

        if not click_tuition_tab(driver):
            raise Exception("Tuition tab not found")

        visible_text = get_visible_expense_text(driver)
        raw = extract_expenses_from_text(university_name, visible_text)
        print("Raw GPT output:\n", raw)

        if raw.startswith("[GPT ERROR]"):
            return [{
                "university": university_name,
                "label": "ERROR",
                "value": "",
                "year": "",
                "error": raw
            }]

        try:
            records = extract_json_or_bullet_points(raw, university_name)
        except Exception as e:
            return [{
                "university": university_name,
                "label": "ERROR",
                "value": "",
                "year": "",
                "error": f"TOTAL ERROR: {e}"
            }]

        results = []
        for rec in records:
            label = rec.get("label", "")
            value = rec.get("value", "")
            year = rec.get("year", "")
            results.append({
                "university": university_name,
                "label": label,
                "value": value,
                "year": year,
                "error": ""
            })

        return results

    except Exception as e:
        return [{
            "university": university_name,
            "label": "ERROR",
            "value": "",
            "year": "",
            "error": f"TOTAL ERROR: {e}"
        }]
    finally:
        driver.quit()

def scrape_all(input_csv, output_csv):
    df = pd.read_csv(input_csv)
    fieldnames = ["university", "label", "value", "year", "error"]

    with open(output_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if f.tell() == 0:
            writer.writeheader()

        for i, row in df.iterrows():
            university = row["university"]
            print(f"\n [{i+1}/{len(df)}] Scraping: {university}")
            results = process_university(university)
            for result in results:
                writer.writerow(result)
            f.flush()
            time.sleep(2)

    print(f"\n Done. Data saved to {output_csv}")

if __name__ == "__main__":
    scrape_all("us_universities.csv", "latest_expenses.csv")