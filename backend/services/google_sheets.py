import os
import json
import base64
import time
import copy
import socket
import logging
import threading
from datetime import datetime

# Set global socket timeout to prevent hung Google API calls
socket.setdefaulttimeout(25)

logger = logging.getLogger(__name__)

# Tab definitions and their exact column headers
SHEET_SCHEMAS = {
    "Members": [
        "Member ID", "Member Name", "Member Code Hash", "Phone Number", 
        "Email", "Location", "Account Status", "Date Created", "Last Login", "Notes"
    ],
    "Orders": [
        "Order ID", "Customer ID", "Member ID", "Order Date", "Order Status", 
        "Total Amount", "Total Amount Paid", "Remaining Amount", "Payment Status", 
        "Verification Status", "Delivery or Collection Details", "Special Instructions", 
        "Created Date", "Updated Date", "Archived Status"
    ],
    "Order_Items": [
        "Order Item ID", "Order ID", "Cake ID", "Cake Name", "Weight", 
        "Quantity", "Unit Price", "Subtotal", "Historical Price"
    ],
    "Customers": [
        "Customer ID", "Customer Name", "Phone Number", "Alternate Phone Number", 
        "Address", "Location", "Landmark", "Notes", "Created Date", "Updated Date", "Archived Status"
    ],
    "Payments": [
        "Payment ID", "Order ID", "Member ID", "Payment Amount", "Payment Date", 
        "Payment Time", "Payment Method", "Payment Reference", "Recorded By", 
        "Verification Status", "Verified By", "Verification Date", "Notes"
    ],
    "Member_Requests": [
        "Request ID", "Applicant Name", "Phone Number", "Location", "Optional Message", 
        "Request Date", "Request Status", "Admin Notes", "Contacted Date", "Approval or Rejection Date"
    ],
    "Cake_Settings": [
        "Cake ID", "Cake Name", "Description", "Available Weights", 
        "Price For Each Weight", "Active Status", "Date Created", "Last Updated"
    ],
    "Locations": [
        "Location ID", "Location Name", "Description", "Active Status"
    ],
    "Custom_Fields": [
        "Field ID", "Field Name", "Field Type", "Required", 
        "Dropdown Options", "Active Status", "Display Order"
    ],
    "Custom_Field_Values": [
        "Value ID", "Order ID", "Field ID", "Field Value", "Created Date"
    ],
    "Activity_Logs": [
        "Log ID", "Admin ID or Username", "Action Type", "Action Description", 
        "Related Record ID", "Previous Value", "New Value", "Date", "Time"
    ],
    "Settings": [
        "Setting ID", "Setting Name", "Setting Value", "Description", "Updated Date"
    ]
}

# Initial seed data for defaults when tabs are freshly created
DEFAULT_SEEDS = {
    "Cake_Settings": [
        [
            "CAKE-001", "Plum Cake (Traditional Christmas)", 
            "Rich festive dry fruits and spices plum cake", 
            json.dumps(["500 g", "1 kg"]), 
            json.dumps({"500 g": 250, "1 kg": 500}), 
            "Active", datetime.now().strftime("%Y-%m-%d"), datetime.now().strftime("%Y-%m-%d")
        ],
        [
            "CAKE-002", "Chocolate Delight Cake", 
            "Premium dark chocolate festive special", 
            json.dumps(["500 g", "1 kg"]), 
            json.dumps({"500 g": 300, "1 kg": 600}), 
            "Active", datetime.now().strftime("%Y-%m-%d"), datetime.now().strftime("%Y-%m-%d")
        ],
        [
            "CAKE-003", "Rich Fruit & Nut Cake", 
            "Loaded with almonds, cashews, and glazed cherries", 
            json.dumps(["500 g", "1 kg"]), 
            json.dumps({"500 g": 280, "1 kg": 550}), 
            "Active", datetime.now().strftime("%Y-%m-%d"), datetime.now().strftime("%Y-%m-%d")
        ]
    ],
    "Locations": [
        ["LOC-001", "Pancode Central", "Parish church & central hall", "Active"],
        ["LOC-002", "North Ward", "Residential area north sector", "Active"],
        ["LOC-003", "South Ward", "Residential area south sector", "Active"],
        ["LOC-004", "East Ward", "East side community", "Active"],
        ["LOC-005", "West Ward", "West side community", "Active"]
    ],
    "Custom_Fields": [
        ["FIELD-001", "Delivery Preference", "Dropdown", "Yes", "Home Delivery, Church Collection, Ward Coordinator Pickup", "Active", "1"],
        ["FIELD-002", "Preferred Delivery Date", "Date", "No", "", "Active", "2"],
        ["FIELD-003", "Special Occasion / Dedication", "Short Text", "No", "", "Active", "3"]
    ],
    "Settings": [
        ["SET-001", "system_title", "Christmas Cake Challenge", "Application title", datetime.now().strftime("%Y-%m-%d")],
        ["SET-002", "campaign_year", "2026", "Current campaign year", datetime.now().strftime("%Y-%m-%d")],
        ["SET-003", "currency_symbol", "₹", "Currency symbol for display", datetime.now().strftime("%Y-%m-%d")],
        ["SET-004", "orders_active", "true", "Whether order submission is open", datetime.now().strftime("%Y-%m-%d")]
    ]
}


class GoogleSheetsService:
    def __init__(self):
        self.spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID", "1HFZzU7EB5cCbZI2BvMFML9JH8ySit7PUBew4Xkql6pI")
        self.service = None
        self._initialized = False
        self._init_error = None
        self._local_storage = {}  # In-memory fallback if credentials not configured yet
        self._lock = threading.RLock()
        self._cache = {}
        self._cache_ttl = 5  # 5 seconds read cache
        self._init_connection()

    def _get_credentials(self):
        """Parse service account credentials from env or file."""
        try:
            from google.oauth2 import service_account
        except ImportError:
            logger.warning("google-auth package not installed. Using local resilient storage.")
            return None

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]

        # 1. Check raw JSON string in env
        sa_json_str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if sa_json_str:
            try:
                # May be base64 encoded
                if sa_json_str.strip().startswith("{"):
                    info = json.loads(sa_json_str)
                else:
                    decoded = base64.b64decode(sa_json_str).decode("utf-8")
                    info = json.loads(decoded)
                return service_account.Credentials.from_service_account_info(info, scopes=scopes)
            except Exception as e:
                logger.error(f"Error parsing GOOGLE_SERVICE_ACCOUNT_JSON: {e}")

        # 2. Check file path in env
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if creds_path and os.path.exists(creds_path):
            try:
                return service_account.Credentials.from_service_account_file(creds_path, scopes=scopes)
            except Exception as e:
                logger.error(f"Error loading credentials from {creds_path}: {e}")

        # 3. Check default local files if present
        current_dir = os.path.dirname(os.path.abspath(__file__))
        backend_dir = os.path.dirname(current_dir)
        root_dir = os.path.dirname(backend_dir)
        local_candidates = [
            os.path.join(backend_dir, "service_account.json"),
            os.path.join(backend_dir, "service_account.json.json"),
            os.path.join(root_dir, "service_account.json"),
            "service_account.json",
            "backend/service_account.json",
            "credentials.json",
            "../service_account.json"
        ]
        for cand in local_candidates:
            if os.path.exists(cand):
                try:
                    return service_account.Credentials.from_service_account_file(cand, scopes=scopes)
                except Exception as e:
                    logger.error(f"Error loading credentials from {cand}: {e}")

        return None

    def _init_connection(self):
        """Initializes Google Sheets API client with retry and fallback."""
        try:
            creds = self._get_credentials()
            if creds:
                try:
                    from googleapiclient.discovery import build
                    self.service = build("sheets", "v4", credentials=creds, cache_discovery=False)
                    self._ensure_all_sheets()
                    self._initialized = True
                    self._init_error = None
                    logger.info(f"Connected to Google Sheets: {self.spreadsheet_id}")
                except ImportError:
                    self._init_error = "google-api-python-client package not installed. Using local resilient storage."
                    logger.warning(self._init_error)
                    self._init_local_fallback()
            else:
                self._init_error = (
                    "Google Sheets credentials not configured. "
                    "Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_APPLICATION_CREDENTIALS."
                )
                logger.warning(self._init_error)
                self._init_local_fallback()
        except Exception as e:
            self._init_error = str(e)
            logger.error(f"Failed to connect to Google Sheets: {e}")
            self._init_local_fallback()

    def _init_local_fallback(self):
        """Prepopulates in-memory storage for offline testing and graceful setup."""
        for sheet_name, headers in SHEET_SCHEMAS.items():
            if sheet_name not in self._local_storage:
                self._local_storage[sheet_name] = [headers]
                if sheet_name in DEFAULT_SEEDS:
                    for row in DEFAULT_SEEDS[sheet_name]:
                        self._local_storage[sheet_name].append(row)

    def is_connected(self):
        """Returns connection status details."""
        return {
            "connected": self.service is not None and self._initialized,
            "spreadsheet_id": self.spreadsheet_id,
            "mode": "Google Sheets API v4" if (self.service and self._initialized) else "Local Resilient Storage (Credentials Pending)",
            "error": self._init_error
        }

    def _retry_api_call(self, func, max_retries=3, initial_delay=1.0):
        """Executes an API call with thread locking and exponential backoff on transient errors."""
        with self._lock:
            delay = initial_delay
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func()
                except Exception as e:
                    last_exception = e
                    logger.warning(f"Google Sheets API call failed (attempt {attempt + 1}/{max_retries}): {e}")
                    time.sleep(delay)
                    delay *= 2
            raise last_exception

    def _ensure_all_sheets(self):
        """Checks for all 12 required tabs and creates missing ones with headers."""
        if not self.service:
            return

        def fetch_meta():
            return self.service.spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()

        meta = self._retry_api_call(fetch_meta)
        existing_sheets = [s["properties"]["title"] for s in meta.get("sheets", [])]

        requests = []
        for sheet_name in SHEET_SCHEMAS.keys():
            if sheet_name not in existing_sheets:
                requests.append({
                    "addSheet": {
                        "properties": {
                            "title": sheet_name,
                            "gridProperties": {
                                "rowCount": 1000,
                                "columnCount": len(SHEET_SCHEMAS[sheet_name]) + 2
                            }
                        }
                    }
                })

        if requests:
            def batch_update():
                return self.service.spreadsheets().batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body={"requests": requests}
                ).execute()

            self._retry_api_call(batch_update)
            logger.info(f"Created missing sheets: {[r['addSheet']['properties']['title'] for r in requests]}")

        # Check and initialize headers for all sheets
        for sheet_name, headers in SHEET_SCHEMAS.items():
            self._ensure_sheet_headers(sheet_name, headers)

    def _ensure_sheet_headers(self, sheet_name, headers):
        """Ensures headers are present in the first row without overwriting existing data."""
        if not self.service:
            return

        def get_header():
            return self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"'{sheet_name}'!A1:Z1"
            ).execute()

        res = self._retry_api_call(get_header)
        values = res.get("values", [])

        if not values or len(values[0]) == 0:
            # Sheet is empty, write headers and default seed data if available
            rows_to_insert = [headers]
            if sheet_name in DEFAULT_SEEDS:
                rows_to_insert.extend(DEFAULT_SEEDS[sheet_name])

            def append_header():
                return self.service.spreadsheets().values().append(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"'{sheet_name}'!A1",
                    valueInputOption="USER_ENTERED",
                    body={"values": rows_to_insert}
                ).execute()

            self._retry_api_call(append_header)
            logger.info(f"Initialized headers and seed data for sheet: {sheet_name}")

    def get_all_records(self, sheet_name):
        """Reads all rows and returns a list of dictionaries mapping header -> value with cache."""
        now = time.time()
        if sheet_name in self._cache:
            cache_time, cached_records = self._cache[sheet_name]
            if now - cache_time < self._cache_ttl:
                return copy.deepcopy(cached_records)

        if not self.service or not self._initialized:
            rows = self._local_storage.get(sheet_name, [])
            if len(rows) <= 1:
                return []
            headers = [h.strip() for h in rows[0]]
            records = []
            for row in rows[1:]:
                rec = {}
                for idx, h in enumerate(headers):
                    rec[h] = row[idx] if idx < len(row) else ""
                records.append(rec)
            self._cache[sheet_name] = (now, records)
            return records

        def fetch():
            return self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"'{sheet_name}'!A:Z"
            ).execute()

        try:
            res = self._retry_api_call(fetch)
            values = res.get("values", [])
            if not values or len(values) <= 1:
                self._cache[sheet_name] = (now, [])
                return []

            headers = [str(h).strip() for h in values[0]]
            records = []
            for row in values[1:]:
                if not any(row):
                    continue
                rec = {}
                for idx, h in enumerate(headers):
                    rec[h] = row[idx] if idx < len(row) else ""
                records.append(rec)
            self._cache[sheet_name] = (now, records)
            return records
        except Exception as e:
            logger.error(f"Error reading records from {sheet_name}: {e}")
            return []

    def append_row(self, sheet_name, row_dict_or_list):
        """Appends a single record or list of values to the specified sheet."""
        self._cache.pop(sheet_name, None)
        headers = SHEET_SCHEMAS.get(sheet_name, [])
        if isinstance(row_dict_or_list, dict):
            row_values = [str(row_dict_or_list.get(h, "")) for h in headers]
        else:
            row_values = [str(v) for v in row_dict_or_list]

        if not self.service or not self._initialized:
            if sheet_name not in self._local_storage:
                self._local_storage[sheet_name] = [headers]
            self._local_storage[sheet_name].append(row_values)
            return True

        def append_call():
            return self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=f"'{sheet_name}'!A1",
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": [row_values]}
            ).execute()

        try:
            self._retry_api_call(append_call)
            return True
        except Exception as e:
            logger.error(f"Error appending row to {sheet_name}: {e}")
            raise e

    def append_rows(self, sheet_name, list_of_dicts_or_rows):
        """Batch appends multiple records."""
        self._cache.pop(sheet_name, None)
        if not list_of_dicts_or_rows:
            return True

        headers = SHEET_SCHEMAS.get(sheet_name, [])
        formatted_rows = []
        for item in list_of_dicts_or_rows:
            if isinstance(item, dict):
                formatted_rows.append([str(item.get(h, "")) for h in headers])
            else:
                formatted_rows.append([str(v) for v in item])

        if not self.service or not self._initialized:
            if sheet_name not in self._local_storage:
                self._local_storage[sheet_name] = [headers]
            self._local_storage[sheet_name].extend(formatted_rows)
            return True

        def batch_append():
            return self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=f"'{sheet_name}'!A1",
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": formatted_rows}
            ).execute()

        try:
            self._retry_api_call(batch_append)
            return True
        except Exception as e:
            logger.error(f"Error batch appending rows to {sheet_name}: {e}")
            raise e

    def update_row(self, sheet_name, id_col_name, id_val, updated_dict):
        """Finds row by ID column value and updates fields."""
        self._cache.pop(sheet_name, None)
        headers = SHEET_SCHEMAS.get(sheet_name, [])

        if not self.service or not self._initialized:
            rows = self._local_storage.get(sheet_name, [])
            if len(rows) <= 1:
                return False
            col_headers = rows[0]
            if id_col_name not in col_headers:
                return False
            id_idx = col_headers.index(id_col_name)
            for r_idx in range(1, len(rows)):
                if len(rows[r_idx]) > id_idx and str(rows[r_idx][id_idx]).strip() == str(id_val).strip():
                    for k, v in updated_dict.items():
                        if k in col_headers:
                            k_idx = col_headers.index(k)
                            while len(rows[r_idx]) <= k_idx:
                                rows[r_idx].append("")
                            rows[r_idx][k_idx] = str(v)
                    return True
            return False

        # Live Google Sheets update
        def fetch_all():
            return self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"'{sheet_name}'!A:Z"
            ).execute()

        res = self._retry_api_call(fetch_all)
        values = res.get("values", [])
        if not values or len(values) <= 1:
            return False

        sheet_headers = [str(h).strip() for h in values[0]]
        if id_col_name not in sheet_headers:
            logger.error(f"Column {id_col_name} not found in {sheet_name}")
            return False

        id_col_idx = sheet_headers.index(id_col_name)
        target_row_num = None
        current_row_data = None

        for idx, row in enumerate(values[1:], start=2):
            if len(row) > id_col_idx and str(row[id_col_idx]).strip() == str(id_val).strip():
                target_row_num = idx
                current_row_data = list(row)
                break

        if not target_row_num:
            logger.warning(f"Record with {id_col_name}={id_val} not found in {sheet_name}")
            return False

        while len(current_row_data) < len(sheet_headers):
            current_row_data.append("")

        for k, v in updated_dict.items():
            if k in sheet_headers:
                idx = sheet_headers.index(k)
                current_row_data[idx] = str(v)

        # Write updated row
        def write_update():
            return self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f"'{sheet_name}'!A{target_row_num}",
                valueInputOption="USER_ENTERED",
                body={"values": [current_row_data]}
            ).execute()

        self._retry_api_call(write_update)
        return True

    def find_record(self, sheet_name, col_name, value):
        """Returns the first matching record dict or None."""
        records = self.get_all_records(sheet_name)
        target = str(value).strip().lower()
        for rec in records:
            if str(rec.get(col_name, "")).strip().lower() == target:
                return rec
        return None

    def find_records(self, sheet_name, filter_fn):
        """Returns all records matching the filter predicate function."""
        records = self.get_all_records(sheet_name)
        return [r for r in records if filter_fn(r)]


# Global singleton instance
sheets_service = GoogleSheetsService()
