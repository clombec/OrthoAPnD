# OrthoAPnD

Django dashboard for prosthesis follow-up.
This projects uses OrthoAGet to retrieve data from OrthoAdvance and displays it through a local webpage.
Development in progress, not for use in Prod/Open environment

## Requirements
- Python 3.11+
- [OrthoAGet](https://github.com/toi/OrthoAGet) installed as editable package

## Setup

git clone https://github.com/toi/OrthoAPnD
cd OrthoAPnD
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and set your SECRET_KEY

python manage.py migrate
python manage.py runserver

## License
AGPL v3 — see LICENSE