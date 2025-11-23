import time
import csv
import random
import re
from collections import Counter
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType

# --- CONFIGURATION ---
START_URL = "https://rivalsmeta.com/leaderboard"
PAGES_TO_SCRAPE = 5
OUTPUT_FILE = "rivalsmeta_top10_roles.csv"


def setup_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--incognito")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )

    return webdriver.Chrome(
        service=Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install()),
        options=options,
    )


def collect_player_links(driver):
    """Phase 1: Collect profile URLs."""
    player_data = []
    print("--- PHASE 1: Collecting URLs ---")

    driver.get(START_URL)
    time.sleep(3)

    for page_num in range(1, PAGES_TO_SCRAPE + 1):
        print(f"Scanning Page {page_num}...")

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "tr"))
            )

            links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/player/']")
            new_count = 0
            for link in links:
                href = link.get_attribute("href")
                name = link.text.strip()
                if href and name and href not in [p["URL"] for p in player_data]:
                    player_data.append(
                        {
                            "Player": name,
                            "URL": href,
                            "Main Role": "Pending",
                            "Vanguard Wins": 0,
                            "Duelist Wins": 0,
                            "Strategist Wins": 0,
                        }
                    )
                    new_count += 1

            print(f"   Found {new_count} new players.")

        except Exception as e:
            print(f"Error on page {page_num}: {e}")

    print(f"Total Unique Players: {len(player_data)}")
    return player_data


def scrape_profile_stats(driver, player_entry):
    """Phase 2: Visit Profile -> Check Private -> Click Heroes -> Read Stats."""
    driver.get(player_entry["URL"])
    time.sleep(random.uniform(2.0, 3.0))

    role_counts = {"Vanguard": 0, "Duelist": 0, "Strategist": 0}

    # --- 1. CHECK FOR PRIVATE PROFILE ---
    try:
        # We grab the body text immediately to see if the "Private" warning exists
        body_text_initial = driver.find_element(By.TAG_NAME, "body").text
        if "This Profile is Private" in body_text_initial:
            return "Private Profile", role_counts
    except Exception:
        pass  # If reading body fails, proceed to try clicking anyway

    try:
        # --- 2. ROBUST TAB CLICKER ---
        possible_selectors = [
            "//a[contains(text(), 'Heroes')]",
            "//div[contains(text(), 'Heroes')]",
            "//span[contains(text(), 'Heroes')]",
            "//*[text()='Heroes']",
        ]

        clicked = False
        for xpath in possible_selectors:
            try:
                elem = WebDriverWait(driver, 2).until(
                    EC.element_to_be_clickable((By.XPATH, xpath))
                )
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", elem
                )
                time.sleep(0.2)
                driver.execute_script("arguments[0].click();", elem)
                WebDriverWait(driver, 3).until(
                    EC.text_to_be_present_in_element((By.TAG_NAME, "body"), "Win Rate")
                )
                clicked = True
                break
            except Exception:
                continue

        if not clicked:
            return "Error (Tab Click)", role_counts

        # --- 3. EXTRACT STATS ---
        body_text = driver.find_element(By.TAG_NAME, "body").text

        for role in role_counts.keys():
            pattern = re.compile(rf"{role}.*?\(\s*(\d+)\s*W", re.IGNORECASE | re.DOTALL)
            match = pattern.search(body_text)
            if match:
                role_counts[role] = int(match.group(1))

    except Exception as e:
        print(f"Error reading stats: {e}")

    max_wins = -1
    main_role = "Unknown"
    for role, wins in role_counts.items():
        if wins > max_wins and wins > 0:
            max_wins = wins
            main_role = role

    if max_wins == -1:
        # If we got here, it's public but had 0 wins found or parsable
        main_role = "Unknown (Public)"

    return main_role, role_counts


def main():
    driver = setup_driver()
    try:
        players = collect_player_links(driver)
        if not players:
            return

        print(f"--- PHASE 2: Visiting {len(players)} Profiles ---")

        for i, player in enumerate(players):
            print(f"[{i+1}/{len(players)}] {player['Player']}...", end=" ")

            main_role, counts = scrape_profile_stats(driver, player)

            player["Main Role"] = main_role
            player["Vanguard Wins"] = counts["Vanguard"]
            player["Duelist Wins"] = counts["Duelist"]
            player["Strategist Wins"] = counts["Strategist"]

            print(f"-> {main_role}")

        keys = [
            "Player",
            "Main Role",
            "Vanguard Wins",
            "Duelist Wins",
            "Strategist Wins",
            "URL",
        ]
        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(players)
        print(f"\nDone! Saved to {OUTPUT_FILE}")

        print("\n--- FINAL ROLE COUNTS ---")
        all_roles = [p["Main Role"] for p in players]
        role_totals = Counter(all_roles)

        for role, count in role_totals.items():
            print(f"{role}: {count}")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
