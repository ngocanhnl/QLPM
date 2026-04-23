## Medical Platform (Flask + MySQL + Bootstrap 5)

### 1) Project structure

```
/app
  /models
    appointment.py
    doctor.py
    enums.py
    schedule.py
    user.py
  /routes
    admin_routes.py
    auth_routes.py
    doctor_routes.py
    patient_routes.py
  /services
    appointment_service.py
    auth_service.py
    authz.py
    doctor_service.py
    forms.py
    schedule_service.py
  /templates
    base.html
    /auth
      login.html
      register.html
    /patient
      booking.html
      dashboard.html
      doctor_detail.html
      search_doctor.html
    /doctor
      appointment_detail.html
      appointments.html
      dashboard.html
      schedule_form.html
      schedules.html
    /admin
      dashboard.html
  /static
config.py
app.py
requirements.txt
/.env.example
/sql
  schema.sql
/scripts
  init_db.py
  seed.py
```

### 2) Prerequisites

- Python 3.11+ (khuyến nghị)
- MySQL 8+

### 3) Create database (SQL script)

Chạy file `sql/schema.sql` trong MySQL:

```sql
SOURCE sql/schema.sql;
```

Hoặc copy/paste nội dung vào MySQL client.

### 3.1) Migration (nếu DB đã tồn tại)

Nếu bạn đã có DB cũ và muốn thêm bảng `hospitals` + quan hệ 1 bệnh viện - nhiều bác sĩ:

```sql
SOURCE sql/migration_add_hospitals.sql;
```

### 4) Configure environment

Tạo file `.env` từ `.env.example` và sửa `DATABASE_URL` đúng MySQL của bạn.

Ví dụ:

```
DATABASE_URL=mysql+pymysql://root:your_password@localhost:3306/medical_platform?charset=utf8mb4
SECRET_KEY=your-secret
```

### 5) Install dependencies

Trong PowerShell tại thư mục project:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 6) Create tables via SQLAlchemy (optional)

Nếu bạn muốn SQLAlchemy tự tạo tables (thay vì chạy SQL script):

```powershell
python .\scripts\init_db.py
```

### 7) Seed sample data

```powershell
python .\scripts\seed.py
```

Tài khoản mẫu được in ra sau khi seed.

### 8) Run server

```powershell
python .\app.py
```

Mở trình duyệt:

- Home/Search: `http://127.0.0.1:3000/doctors/search`
- Login: `http://127.0.0.1:3000/auth/login`

### 9) Notes (roles)

- **PATIENT**: search doctors, view profile/slots, book appointment, xem dashboard
- **DOCTOR**: CRUD schedules, xem & cập nhật trạng thái appointments
- **ADMIN**: xem danh sách users (màn admin dashboard)

## VNPay integration (nhúng thanh toán)

### 1) Cấu hình `.env`
Thêm các biến sau:
```
VNPAY_TMN_CODE=your_tmn_code
VNPAY_HASH_SECRET=your_hash_secret
VNPAY_PAYMENT_URL=https://sandbox.vnpayment.vn/paymentv2/vpcpay.html
VNPAY_VERSION=2.1.0
VNPAY_LOCALE=vn
VNPAY_CURR_CODE=VND
VNPAY_ORDER_TYPE=other
```

### 2) Tạo bảng `payment_transactions`
Chạy migration:
```sql
SOURCE sql/migration_add_payment_transactions.sql;
```

### 3) Flow đặt lịch
- Người bệnh nhấn `Pay & Book` trên trang bác sĩ
- Hệ thống redirect sang VNPay để thanh toán
- VNPay callback về `/vnpay/return`
- Nếu `vnp_ResponseCode=00` và `vnp_SecureHash` hợp lệ => tạo appointment trạng thái `PENDING`

