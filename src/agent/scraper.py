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
import httpx
from dotenv import load_dotenv

load_dotenv()


def extract_expenses_from_text(university_name, visible_text):
    system_prompt = (
        "You are a tuition extraction assistant. Your goal is to extract the Total Estimated Annual Cost "
        "(Cost of Attendance or Net Price) for the most recent academic year (e.g., 2024–2025). "
        "Prioritize any row labeled 'Total', 'Cost of Attendance', or 'Net Price'. "
        "If no such total is found, calculate it by summing recurring costs like: "
        "tuition, fees, housing, meals, books, and personal expenses. "
        "Ignore one-time or optional costs like application fees, tech fees, or parking. "
        "Return only a JSON list with keys: label, value, and year."
    )

    chunks = textwrap.wrap(visible_text, width=3000, break_long_words=False, replace_whitespace=False)
    messages = [{"role": "system", "content": system_prompt}]
    for chunk in chunks[:-1]:
        messages.append({"role": "user", "content": f"(Partial chunk from {university_name}):\n{chunk}"})
    messages.append({"role": "user", "content": f"(Final chunk from {university_name}):\n{chunks[-1]}"})

    try:
        headers = {
            "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
            "User-Agent": "university-cost-scraper"
        }

        response = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json={
                "model": "deepseek/deepseek-chat",
                "messages": messages,
                "temperature": 0,
                "max_tokens": 2048,
            },
            timeout=60
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

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

        try:
            WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "Tuition"))).click()
            print(" Clicked Tuition tab")
        except:
            print(" Tuition tab not found by direct text, using fallback...")
            for link in driver.find_elements(By.TAG_NAME, "a"):
                if "tuition" in link.text.lower() or "fees" in link.text.lower():
                    driver.execute_script("arguments[0].scrollIntoView(true);", link)
                    time.sleep(0.5)
                    link.click()
                    print(f"Fallback clicked: {link.text}")
                    break

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

        cleaned = re.sub(r"```(json)?", "", raw).strip()
        match = re.search(r"\[\s*{.*?}\s*]", cleaned, re.DOTALL)
        if not match:
            raise ValueError("No JSON array found in GPT output")

        json_str = match.group(0)
        try:
            records = json.loads(json_str)
        except json.JSONDecodeError:
            records = ast.literal_eval(json_str)

        def extract_year(rec):
            year_text = rec.get("year", "")
            match = re.search(r"20\d{2}", str(year_text))
            return int(match.group()) if match else 0

        total_rows = sorted(
            [r for r in records
             if "total" in r.get("label", "").lower()
             or "cost of attendance" in r.get("label", "").lower()
             or "net price" in r.get("label", "").lower()],
            key=extract_year,
            reverse=True
        )

        if total_rows:
            results = []
            for row in total_rows:
                results.append({
                    "university": university_name,
                    "label": row.get("label", ""),
                    "value": row.get("value", ""),
                    "year": row.get("year", ""),
                    "error": ""
                })
            return results

        valid_keywords = ["tuition", "housing", "meals", "food", "books", "supplies", "personal", "misc", "room", "board"]
        cost_values = []

        for row in records:
            label = row.get("label", "").lower()
            value = row.get("value", "")
            try:
                if any(k in label for k in valid_keywords):
                    if isinstance(value, (int, float)):
                        numeric = float(value)
                    elif isinstance(value, str):
                        numeric = float(value.replace("$", "").replace(",", "").strip())
                    else:
                        continue
                    cost_values.append(numeric)
            except:
                continue

        if cost_values:
            total_cost = round(sum(cost_values), 2)
            return [{
                "university": university_name,
                "label": "Average Annual Cost",
                "value": f"${total_cost:,.2f}",
                "year": "",
                "error": ""
            }]
        else:
            return [{
                "university": university_name,
                "label": "Average Annual Cost",
                "value": "",
                "year": "",
                "error": "No valid cost values found"
            }]

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
