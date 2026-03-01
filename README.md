# ImplantDB

A web application for tracking dental implant inventory by size and brand. Built for dental practices that need a simple, reliable way to monitor stock levels and get alerted when supplies run low.

## Features

- **Inventory tracking** — Track implants by size (e.g. 4.5x11.5) and brand
- **Stock management** — Use implants (decrement by 1), add stock, or set arbitrary quantities
- **Low stock alerts** — Set a minimum stock threshold per SKU; the dashboard highlights items running low
- **Filtering** — Filter inventory by size or brand
- **Multi-user** — Each user has their own isolated inventory
- **Account management** — Change password or delete account from the profile page

## Tech Stack

- **Backend:** Flask 3, SQLAlchemy, SQLite
- **Auth:** Flask-Login, Werkzeug password hashing
- **Frontend:** Jinja2 templates, Bootstrap 5.3 (grid/utilities), custom CSS
- **Theme:** Slate — light mode, cool blue-grey background, dark navy headers, steel blue accent, Cinzel/Lora/DM Sans fonts

## Getting Started

### Requirements

- Python 3.14+
- [`uv`](https://github.com/astral-sh/uv) (recommended) or pip

### Install & Run

```bash
git clone <repo-url>
cd ImplantDB

# Install dependencies
uv sync

# Create a .env file with a secret key
echo "SECRET_KEY=your-secret-key-here" > .env

# Run the app
uv run flask run
```

The app will be available at `http://localhost:5000`.

## Data Model

### Implant

| Field | Type | Description |
|-------|------|-------------|
| `size` | String | Implant dimensions, e.g. `4.5x11.5` |
| `brand` | String | Manufacturer (Hiossen, Megagen, Astra, or custom) |
| `stock` | Integer | Current quantity on hand |
| `min_stock` | Integer | Low stock alert threshold |

## Routes

| Route | Description |
|-------|-------------|
| `/` | Inventory dashboard |
| `/add` | Add a new implant SKU |
| `/edit/<id>` | Edit implant details |
| `/use/<id>` | Decrement stock by 1 |
| `/add_stock/<id>` | Add quantity to stock |
| `/remove/<id>` | Delete an implant |
| `/update_min_stock/<id>` | Update minimum stock threshold |
| `/profile` | Change password / delete account |
| `/procedures` | Procedure log |
| `/procedures/new` | Log a new procedure |
| `/procedures/<id>/edit` | Edit a procedure |

## Deployment Notes

- The SQLite database is stored in the `instance/` folder (gitignored)
- Set `SECRET_KEY` in `.env` — never use the default in production
- The app includes Werkzeug's `ProxyFix` middleware for use behind a reverse proxy (nginx, Caddy, etc.)
