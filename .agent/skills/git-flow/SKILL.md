---
name: git-flow
description: Vaste Git-workflow voor dit Python-project met richtlijnen voor branching, stapsgewijze commits, conflictbeheersing en Pull Requests.
---

# 🌿 Git Flow voor SoundCloud Scraper

Deze skill beschrijft de verplichte Git-workflow voor alle ontwikkelwerkzaamheden binnen dit Python-project. Volg deze stappen altijd nauwkeurig en wijk hier niet van af.

---

## 1. Statuscontrole & Branchbescherming
* Controleer altijd eerst de huidige status van de werkmap:
  ```bash
  git status
  ```
* Zorg dat de repository schoon is en er geen onbedoelde wijzigingen rondslingeren.
* **Belangrijk:** Werk **nooit direct op `main`**. De `main`-branch dient altijd stabiel en productiewaardig te blijven.

---

## 2. Nieuwe branch aanmaken
* Zorg dat je lokale `main` up-to-date is en vertak altijd vanaf `main` naar een specifieke taakbranch:
  ```bash
  git checkout main
  git pull origin main
  ```
* Gebruik een duidelijke prefix afhankelijk van het type werk:
  * **Nieuwe features:** `feat/<korte-beschrijving>` (bijv. `feat/scraper-improvements`)
  * **Bugfixes:** `fix/<korte-beschrijving>` (bijv. `fix/timeout-handling`)
  * **Documentatie/Refactor:** `docs/<onderwerp>` of `refactor/<onderwerp>`
* Maak de branch aan en wissel er direct naartoe:
  ```bash
  git checkout -b <branch-naam>
  ```

---

## 3. Stapsgewijs werken & kleine commits
* Werk incrementeel: rond eerst één specifieke subtaak af voordat je aan de volgende begint.
* Maak direct na afronding van elke subtaak een kleine, duidelijke lokale commit (bij voorkeur volgens Conventional Commits, bijv. `feat: ...`, `fix: ...`, `refactor: ...`).
* **Strikte staging-regels:** Voorkom dat tijdelijke of gegenereerde bestanden in Git belanden. Stage **nooit**:
  * Python cachebestanden: `__pycache__/`, `*.pyc`
  * Omgevingsvariabelen & geheimen: `.env`, `.env.local`
  * Gedownloade mediabestanden: `*.mp3`, `*.ogg`, `*.wav`
* Controleer vóór elke commit altijd wat je gaat toevoegen:
  ```bash
  git status
  git diff --staged
  git commit -m "<type>: <korte beschrijving van de wijziging>"
  ```

---

## 4. Updates ophalen & Conflictbeheersing
* Haal altijd de meest recente wijzigingen van de remote op vóórdat je gaat pushen:
  ```bash
  git fetch origin
  ```
* Controleer of er wijzigingen op `origin/main` zijn die kunnen conflicteren met jouw branch.
* **⚠️ Strikte stopregel bij merge conflicts:**
  * Als er een merge conflict optreedt of dreigt op te treden: **stop onmiddellijk**.
  * Ga het conflict **niet** zelfstandig oplossen of bestanden aanpassen.
  * Rapporteer het conflict direct en duidelijk aan de gebruiker en vraag om instructies.

---

## 5. Pushen & Pull Request openen
* Push de branch met upstream-tracking naar GitHub:
  ```bash
  git push -u origin <branch-naam>
  ```
* Open direct na het pushen een Pull Request richting `main` met behulp van de GitHub CLI (`gh`):
  ```bash
  gh pr create --base main --head <branch-naam> --title "<Nederlandstalige titel>" --body "<Nederlandstalige samenvatting van de wijzigingen>"
  ```
* **Eisen voor het Pull Request:**
  * Zowel de **titel** als de **beschrijving/samenvatting** moeten in correct Nederlands zijn geschreven.
  * Som in de samenvatting puntsgewijs op wat er is toegevoegd, gewijzigd of opgelost.
