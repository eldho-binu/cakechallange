# Christmas Cake Challenge — Order Management System
**Church Youth Group, Pancode**

A complete, professional, responsive web application built to streamline and replace the manual Excel-based Christmas cake order collection and tracking process.

---

## 1. Project Overview

The **Christmas Cake Challenge – Order Management System** provides:
- **For Youth Group Members**: A mobile-first, easy-to-use ordering interface to record customer details, select multiple cake varieties and weights, calculate order balances, collect advance payments, and monitor personal sales.
- **For Church Administrators**: Complete operational oversight with a Master Order Search, live KPI analytics, customer registry, member management, location management, dynamic cake varieties and pricing, dynamic order custom fields, payment verification, audit trail, and complete 9-worksheet Microsoft Excel downloads.
- **Persistent Database**: Google Sheets API v4 across 12 dedicated tabs with automatic schema and header initialization, batch reads/writes, server-side data validation, and retry backoff.
- **Email Notifications**: Instant email alerts via Resend when new members apply for system access.
- **Vercel Serverless Ready**: Completely decoupled `frontend/` and `backend/` architectures designed for seamless independent deployment on Vercel.

---

## 2. Key Features

### Member Portal
- **Step-by-Step Order Entry Wizard**:
  - **Step 1 — Customer Info**: Customer name, phone number, alternate phone, delivery address, ward/location, and landmark. Includes live phone-number autocomplete search to reuse existing customer records and avoid duplicate data.
  - **Step 2 — Dynamic Cake Items**: Choose cake varieties, select weights (e.g. 500 g, 1 kg), set quantities, and calculate subtotals. Official prices are fetched from admin settings and enforced on the server. Includes "+ Add Another Cake" to add multiple cake items to a single order.
  - **Step 3 — Payment Entry**: Instant live breakdown: Total Order Amount, Advance Paid, and Remaining Balance. Automatic payment status calculation (`Paid`, `Partially Paid`, `Not Paid`).
  - **Step 4 — Additional Information**: Delivery/collection instructions and dynamic custom fields created by the administrator (e.g. Delivery Preference, Preferred Date, Special Dedication).
  - **Step 5 — Review & Confirmation**: Complete order summary before atomic commit to Google Sheets.
- **My Orders**: Filter orders by customer name, phone, order ID, payment status, and verification status. View order details and record additional payments.
- **My Reports**: Personal sales KPIs (Total Orders, Total Cakes Sold, Gross Sales, Collected, Pending) and one-click private Excel export of personal orders.

### Administrator Portal
- **Executive Dashboard**: Real-time sales metrics, collection totals, pending balances, cake variety distribution bar chart, ward/location sales breakdown, and youth member leaderboard.
- **Master Order Search**: Global search across Customer Name, Phone, Alternate Phone, Order ID, Member Name, Location, Cake Type, Weight, Payment Status, Verification Status, and Date Range.
- **Order Management**: Edit customer information, reassign orders to different members, update delivery notes, verify payments, reopen locked orders, archive, and restore records.
- **Customer Management**: Central parish customer directory with order counts, contact details, edit modal, and order history.
- **Member Management**: Create new members, hash login codes with PBKDF2, regenerate codes, activate/deactivate accounts, and monitor individual performance.
- **Member Requests**: Review public access applications, mark as contacted, reject, or approve into active accounts with auto-generated member codes.
- **Location Management**: Standardized church wards and parishes with sales totals and collection balances.
- **Dynamic Cake Settings**: Add/edit cake varieties, configure weights, adjust prices in Indian Rupees (₹), and activate/deactivate varieties without modifying code. Historical order prices are permanently preserved.
- **Dynamic Custom Fields**: Add custom fields (Short Text, Long Text, Number, Dropdown, Date, Yes/No) that automatically appear on member order forms.
- **Payment Verification**: Review recorded payments, verify or reject transactions, and recalculate customer balances automatically.
- **Reports & Excel Exports**: One-click download of the **Complete 9-Worksheet Master Excel Workbook** (`openpyxl` formatted with INR currency, auto-fitted columns, zebra striping, and summary totals).
- **Activity Logs**: Immutable security audit trail recording logins, order edits, price changes, payment verifications, and report downloads.
- **Settings & Diagnostics**: Live Google Sheets status check, admin password update, and frontend API URL configurator.

---

## 3. Technology Stack

- **Frontend**: HTML5, Modern CSS3 (Festive Christmas Theme: Forest Green `#14452F`, Berry Red `#C41E3A`, Gold `#D4AF37`, Cream `#FDFBF7`), Vanilla JavaScript (ES6+), Responsive Mobile-First Design.
- **Backend**: Python 3.12, Flask, Flask-CORS, REST API architecture.
- **Database**: Google Sheets API v4 (Spreadsheet ID: `1HFZzU7EB5cCbZI2BvMFML9JH8ySit7PUBew4Xkql6pI`).
- **Reporting**: `openpyxl` for multi-tab Microsoft Excel generation.
- **Authentication**: JWT (JSON Web Tokens) with HS256, PBKDF2-HMAC-SHA256 password/code hashing, rate-limiting brute force protection.
- **Email Service**: Resend API v2 for new member request notifications.
- **Deployment**: Vercel Serverless (Separate `frontend/` and `backend/` projects).

---

## 4. Folder Structure

```text
christmas-cake-challenge/
│
├── frontend/
│   ├── index.html                   # Landing page with live status and quick navigation
│   ├── login.html                   # Member Login, Admin Login & Access Request form
│   ├── dashboard.html               # Member Dashboard with 5 KPI cards & recent orders
│   ├── add-order.html               # 5-Step Order Entry Wizard with live calculations
│   ├── my-orders.html               # Member orders list, search, details & payment entry
│   ├── reports.html                 # Member reports & personal Excel download
│   │
│   ├── admin/
│   │   ├── dashboard.html           # Admin KPIs, real-time distribution charts
│   │   ├── orders.html              # Master Order Search & full order control
│   │   ├── customers.html           # Customer directory & order history
│   │   ├── members.html             # Member management & code regeneration
│   │   ├── requests.html            # Public access applications & approval flow
│   │   ├── locations.html           # Church wards & location management
│   │   ├── cake-settings.html       # Dynamic cake varieties, weights & prices
│   │   ├── custom-fields.html       # Dynamic order form custom fields
│   │   ├── payments.html            # Payment tracking & verification
│   │   ├── reports.html             # Admin reports & 9-worksheet Excel workbook
│   │   ├── activity-logs.html       # Audit trail & system change history
│   │   └── settings.html            # Admin password & Google Sheets diagnostics
│   │
│   ├── css/
│   │   ├── style.css                # Master Christmas design system & components
│   │   └── admin.css                # Admin layout, sidebar, topbar & charts
│   │
│   ├── js/
│   │   ├── config.js                # API Base URL and application settings
│   │   ├── api.js                   # Authenticated fetch wrapper with Bearer token
│   │   ├── auth.js                  # Session & role-based authentication guard
│   │   └── ui.js                    # Toasts, modals, formatters & status pills
│   │
│   └── vercel.json                  # Frontend Vercel routing & security headers
│
├── backend/
│   ├── api/
│   │   └── index.py                 # Flask serverless entry point exposing all REST APIs
│   │
│   ├── services/
│   │   ├── google_sheets.py         # Google Sheets API v4 integration & 12 tab schemas
│   │   ├── authentication.py        # Token generation, PBKDF2 hashing, rate limiting
│   │   ├── order_service.py         # Order calculation, customer lookup, cake validation
│   │   ├── payment_service.py       # Payment recording, balance calculation & verification
│   │   ├── email_service.py         # Resend notification email service
│   │   └── excel_service.py         # openpyxl 9-tab Master Workbook generator
│   │
│   ├── requirements.txt             # Python dependencies
│   └── vercel.json                  # Python Serverless Vercel configuration
│
├── README.md                        # Complete project documentation
└── .gitignore                       # Git ignore rules
```

---

## 5. Google Sheets Database Architecture

Spreadsheet Link: [Google Sheets Database](https://docs.google.com/spreadsheets/d/1HFZzU7EB5cCbZI2BvMFML9JH8ySit7PUBew4Xkql6pI/edit?usp=sharing)  
Spreadsheet ID: `1HFZzU7EB5cCbZI2BvMFML9JH8ySit7PUBew4Xkql6pI`

The application automatically verifies and initializes the following 12 tabs with headers on startup without touching existing records:

| # | Tab Name | Columns Stored |
|---|---|---|
| 1 | `Members` | Member ID, Member Name, Member Code Hash, Phone Number, Email, Location, Account Status, Date Created, Last Login, Notes |
| 2 | `Orders` | Order ID, Customer ID, Member ID, Order Date, Order Status, Total Amount, Total Amount Paid, Remaining Amount, Payment Status, Verification Status, Delivery or Collection Details, Special Instructions, Created Date, Updated Date, Archived Status |
| 3 | `Order_Items` | Order Item ID, Order ID, Cake ID, Cake Name, Weight, Quantity, Unit Price, Subtotal, Historical Price |
| 4 | `Customers` | Customer ID, Customer Name, Phone Number, Alternate Phone Number, Address, Location, Landmark, Notes, Created Date, Updated Date, Archived Status |
| 5 | `Payments` | Payment ID, Order ID, Member ID, Payment Amount, Payment Date, Payment Time, Payment Method, Payment Reference, Recorded By, Verification Status, Verified By, Verification Date, Notes |
| 6 | `Member_Requests` | Request ID, Applicant Name, Phone Number, Location, Optional Message, Request Date, Request Status, Admin Notes, Contacted Date, Approval or Rejection Date |
| 7 | `Cake_Settings` | Cake ID, Cake Name, Description, Available Weights, Price For Each Weight, Active Status, Date Created, Last Updated |
| 8 | `Locations` | Location ID, Location Name, Description, Active Status |
| 9 | `Custom_Fields` | Field ID, Field Name, Field Type, Required, Dropdown Options, Active Status, Display Order |
| 10 | `Custom_Field_Values`| Value ID, Order ID, Field ID, Field Value, Created Date |
| 11 | `Activity_Logs` | Log ID, Admin ID or Username, Action Type, Action Description, Related Record ID, Previous Value, New Value, Date, Time |
| 12 | `Settings` | Setting ID, Setting Name, Setting Value, Description, Updated Date |

---

## 6. How to Set Up Google Cloud & Google Sheets API

Follow these step-by-step instructions:

1. **Open Google Cloud Console**:
   Go to [https://console.cloud.google.com/](https://console.cloud.google.com/) and create a project (e.g. `Christmas-Cake-Challenge`).
2. **Enable APIs**:
   - Go to **APIs & Services** > **Library**.
   - Search for **Google Sheets API** and click **Enable**.
   - Search for **Google Drive API** and click **Enable**.
3. **Create Service Account**:
   - Go to **IAM & Admin** > **Service Accounts**.
   - Click **Create Service Account**.
   - Give it a name (e.g. `cake-sheets-service`).
   - Click **Create and Continue**, then click **Done**.
4. **Download Service Account Key**:
   - Click on the newly created service account email.
   - Go to the **Keys** tab.
   - Click **Add Key** > **Create new key**.
   - Choose **JSON** and download the file.
5. **Share the Google Spreadsheet with the Service Account**:
   - Open the downloaded JSON file and copy the `client_email` address (e.g. `cake-sheets-service@your-project.iam.gserviceaccount.com`).
   - Open the spreadsheet:  
     `https://docs.google.com/spreadsheets/d/1HFZzU7EB5cCbZI2BvMFML9JH8ySit7PUBew4Xkql6pI/edit`
   - Click the blue **Share** button in the top right.
   - Paste the service account email, select **Editor** permissions, uncheck notify, and click **Share**.

---

## 7. How to Set Up Resend for Email Notifications

1. Go to [https://resend.com](https://resend.com) and create an account or log in.
2. Go to **API Keys** and click **Create API Key**.
3. Copy your API Key (e.g. `re_123456789...`).
4. Set the following environment variables on your backend:
   ```env
   RESEND_API_KEY=re_your_api_key_here
   RESEND_FROM_EMAIL=onboarding@resend.dev
   MASTER_ADMIN_EMAIL=margregoriousyouthpancode123@gmail.com
   ```
   *(For custom domain senders, verify your church domain in Resend and replace `onboarding@resend.dev` with e.g. `orders@yourchurch.org`)*.

---

## 8. Initial Administrator Setup

- **Master Administrator Email**:
  ```text
  margregoriousyouthpancode123@gmail.com
  ```
- **Initial Default Password**:
  ```text
  Admin@Christmas2026!
  ```
  *(Can also be customized by setting the `ADMIN_PASSWORD` environment variable or updated at any time from `admin/settings.html`)*.

---

## 9. Environment Variables Reference

### Backend Environment Variables (`backend/.env` or Vercel Project Settings):

```env
# Master Administrator
MASTER_ADMIN_EMAIL=margregoriousyouthpancode123@gmail.com
ADMIN_PASSWORD=Admin@Christmas2026!
SECRET_KEY=your-secure-jwt-random-secret-key-2026

# Google Sheets Database
GOOGLE_SPREADSHEET_ID=1HFZzU7EB5cCbZI2BvMFML9JH8ySit7PUBew4Xkql6pI
GOOGLE_SERVICE_ACCOUNT_JSON={"type": "service_account", "project_id": "...", ...}

# Resend Email Integration
RESEND_API_KEY=re_your_resend_api_key
RESEND_FROM_EMAIL=Christmas Cake Challenge <onboarding@resend.dev>

# Frontend URL for CORS
FRONTEND_URL=https://your-frontend.vercel.app
```

> **Note on `GOOGLE_SERVICE_ACCOUNT_JSON`**: You can paste the entire single-line JSON string, or pass a base64 encoded string of the JSON. Alternatively, when developing locally, you can place your `service_account.json` file inside the `backend/` directory.

### Frontend Configuration:

When deploying frontend and backend to separate Vercel domains, open `admin/settings.html` or set in browser localStorage:
```text
API_BASE_URL=https://your-backend.vercel.app
```
By default, when running on `localhost`, the frontend automatically communicates with `http://localhost:5000`.

---

## 10. Running the Application Locally

### Running the Flask Backend:

1. Open PowerShell or Terminal and navigate to the backend directory:
   ```powershell
   cd backend
   ```
2. Create and activate a Python virtual environment (recommended):
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```
3. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
4. Run the Flask development server:
   ```powershell
   python api/index.py
   ```
   The backend API will start at: `http://localhost:5000`  
   Verify by opening: `http://localhost:5000/api/system/status`

### Running the Frontend:

The frontend uses Vanilla JavaScript, CSS3, and HTML5 with no build step required.

1. Open a new terminal in the `frontend` directory:
   ```powershell
   cd frontend
   ```
2. Start any local static HTTP server, for example with Python:
   ```powershell
   python -m http.server 3000
   ```
   Or with Node:
   ```powershell
   npx serve .
   ```
3. Open your browser and navigate to:
   ```text
   http://localhost:3000
   ```
   The frontend automatically connects to the backend at `http://localhost:5000`.

---

## 11. Deploying to Vercel

The project is structured for independent deployment as two separate Vercel projects:

### Deploying the Backend:

1. Import your GitHub repository into Vercel.
2. In Project Settings:
   - **Root Directory**: `backend`
   - **Framework Preset**: Other (Vercel automatically detects `@vercel/python` from `vercel.json`)
3. Add the **Environment Variables**:
   - `MASTER_ADMIN_EMAIL`: `margregoriousyouthpancode123@gmail.com`
   - `ADMIN_PASSWORD`: Your chosen secure password
   - `SECRET_KEY`: A random 32+ character string
   - `GOOGLE_SPREADSHEET_ID`: `1HFZzU7EB5cCbZI2BvMFML9JH8ySit7PUBew4Xkql6pI`
   - `GOOGLE_SERVICE_ACCOUNT_JSON`: The raw JSON string of your Google service account
   - `RESEND_API_KEY`: Your Resend API key
   - `RESEND_FROM_EMAIL`: `onboarding@resend.dev`
4. Click **Deploy**. Note your deployed backend URL (e.g. `https://cake-backend.vercel.app`).

### Deploying the Frontend:

1. Create a second project on Vercel importing the same repository.
2. In Project Settings:
   - **Root Directory**: `frontend`
   - **Framework Preset**: Other / Static
3. Click **Deploy**.
4. Once deployed, open your frontend site in your browser.
5. Go to `admin/settings.html`, paste your backend URL into the **Backend Base URL** setting, and click **Save API URL**.

---

## 12. Backup and Disaster Recovery

Because Google Sheets is the primary persistent database:
1. **Google Sheets Version History**:
   - Open the Google Spreadsheet.
   - Go to **File** > **Version history** > **See version history**.
   - You can review and restore any cell or tab changes from any point in time.
2. **Scheduled Automated Backup**:
   - Open the Admin Portal > **Reports & Excel**.
   - Click **Download Complete Master Workbook (.xlsx)** to download a complete offline snapshot with all 9 worksheets anytime.
3. **Manual Sheet Duplicate**:
   - In Google Sheets, click **File** > **Make a copy** before campaign milestones.

---

## 13. System Verification & Test Checklist

- [x] **Admin Login**: Log in with `margregoriousyouthpancode123@gmail.com` and default password.
- [x] **Public Member Request**: Fill out access request form; verify record appears in `Member_Requests` and Resend notification triggers.
- [x] **Request Approval**: Admin approves request; unique member code is generated and displayed.
- [x] **Member Login**: Member logs in with Member Name and unique code. Deactivated members are rejected.
- [x] **Step-by-Step Order Creation**:
  - Customer phone autofill search prevents duplicate customers.
  - Adding multiple cake varieties and weights computes subtotals and totals accurately.
  - Advance payment updates remaining balance live.
  - Dynamic custom fields appear automatically and validate required inputs.
- [x] **Multi-Sheet Google Persistence**:
  - `Orders`, `Order_Items`, `Payments`, and `Custom_Field_Values` tabs are written simultaneously.
- [x] **Payment Verification**: Admin marks payment as `Verified` or `Rejected`; order balance updates automatically.
- [x] **Excel Exports**:
  - Member can download only their own orders.
  - Admin can export the full 9-worksheet Master Workbook with styling and INR formatting.
- [x] **Audit Trail**: Every admin login, member update, order creation, and payment action is recorded in `Activity_Logs`.
- [x] **Mobile Responsiveness**: Tested across desktop and mobile screens with touch-friendly navigation and cards.
