import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import date

st.set_page_config(page_title="Kosárlabda eredmény és stat kereső", layout="wide")

st.title("🏀 Kosárlabda mérkőzés kereső – dátum + csapatnév alapján")

# --- 1. Dátum kiválasztása ---------------------------------------------------
selected_date = st.date_input("Válaszd ki a mérkőzés napját:", value=date.today())


# --- 2. Források listája ----------------------------------------------------
SOURCES = ["Sofascore", "FIBA", "Euroleague", "RealGM"]


# --- 3. Kereső funkciók ------------------------------------------------------

def search_sofascore(team, day):
    """
    Sofascore keresés – az adott napon játszott meccseket listázza.
    """
    try:
        api_url = f"https://www.sofascore.com/api/v1/team-search/{team}"
        r = requests.get(api_url, timeout=5)
        if r.status_code != 200:
            return []

        data = r.json().get("teams", [])
        if not data:
            return []

        results = []
        for t in data:
            team_id = t.get("id")
            if not team_id:
                continue

            # Csapat meccsei az adott napon
            match_url = (
                f"https://www.sofascore.com/api/v1/team/{team_id}/events/"
                f"date/{day.year}-{day.month:02}-{day.day:02}"
            )
            matches = requests.get(match_url, timeout=5).json().get("events", [])

            for m in matches:
                results.append({
                    "source": "Sofascore",
                    "home": m["homeTeam"]["name"],
                    "away": m["awayTeam"]["name"],
                    "score": f'{m.get("homeScore",{}).get("current","?")} - '
                             f'{m.get("awayScore",{}).get("current","?")}',
                    "match_id": m["id"]
                })
        return results
    except:
        return []


def search_fiba(team, day):
    """
    Keresés FIBA oldalakon.
    """
    try:
        url = f"https://www.fiba.basketball/search?q={team}"
        html = requests.get(url, timeout=5).text
        soup = BeautifulSoup(html, "html.parser")

        links = soup.select("a")
        results = []

        for a in links:
            href = a.get("href", "")
            if "/game/" in href and str(day.year) in href:
                # próbáljuk kinyerni a csapatneveket
                text = a.text.strip()
                if "-" in text:
                    home, away = text.split("-", 1)
                    results.append({
                        "source": "FIBA",
                        "home": home.strip(),
                        "away": away.strip(),
                        "score": "?",
                        "match_id": href
                    })
        return results
    except:
        return []


def search_realgm(team, day):
    """
    Keresés RealGM oldalakon.
    """
    try:
        url = f"https://basketball.realgm.com/search?q={team}"
        html = requests.get(url, timeout=5).text
        soup = BeautifulSoup(html, "html.parser")

        results = []

        rows = soup.select("a")
        for a in rows:
            text = a.text.strip()
            if "-" in text and any(x.isdigit() for x in text):
                # formátum pl: Team A 82 - 77 Team B
                parts = text.split("-")
                if len(parts) == 2:
                    results.append({
                        "source": "RealGM",
                        "home": parts[0].strip(),
                        "away": parts[1].strip(),
                        "score": "?",
                        "match_id": a.get("href", "")
                    })
        return results
    except:
        return []


def search_all(team, day):
    results = []
    results += search_sofascore(team, day)
    results += search_fiba(team, day)
    results += search_realgm(team, day)
    return results


# --- 4. Input mező -----------------------------------------------------------

team_input = st.text_input("Írd be a csapat nevét (pl. Partizan, Bayern, Szolnok, Falco stb.):")

if team_input:
    matches = search_all(team_input, selected_date)

    if not matches:
        st.error("Nem található ilyen csapat ezen a napon. Próbáld meg másképp beírni (pl. teljes név).")
    else:
        st.success(f"{len(matches)} találat érkezett. Válaszd ki a neked megfelelőt!")

        df = pd.DataFrame(matches)
        choice = st.radio("Válassz mérkőzést:", df.index, format_func=lambda i: f"{df.iloc[i]['home']} - {df.iloc[i]['away']} ({df.iloc[i]['source']})")

        chosen = df.iloc[choice]

        st.subheader("📌 Kiválasztott mérkőzés")
        st.write(f"**{chosen['home']} – {chosen['away']}**")
        st.write(f"Eredmény: **{chosen['score']}**")
        st.write(f"Forrás: {chosen['source']}")

        st.markdown("---")
        st.subheader("📊 Játékos statisztika")

        # --- stat keresés ---
        stats_loaded = False

        # Sofascore stat lekérdezés
        if chosen["source"] == "Sofascore":
            try:
                stat_url = f"https://www.sofascore.com/api/v1/event/{chosen['match_id']}/statistics"
                r = requests.get(stat_url, timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    players = []

                    for team_block in data.get("statistics", []):
                        team_name = team_block["team"]["name"]
                        for p in team_block["players"]:
                            players.append({
                                "Csapat": team_name,
                                "Játékos": p["player"]["name"],
                                "Pont": p.get("points", "?"),
                                "Assziszt": p.get("assists", "?"),
                                "Lepattanó": p.get("rebounds", "?")
                            })
                    st.dataframe(pd.DataFrame(players))
                    stats_loaded = True
            except:
                pass

        # Ha nincs stat
        if not stats_loaded:
            st.warning("📌 **Statisztika betöltése sikertelen**")

        st.markdown("### Források")
        st.write("- Sofascore  
- FIBA  
- RealGM")

