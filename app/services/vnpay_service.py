import hashlib
import hmac
import uuid
from typing import Any
from urllib.parse import quote_plus
from datetime import datetime, timedelta

def _quote(val: Any) -> str:
    # VNPay reference implementation uses URLEncoder.encode (application/x-www-form-urlencoded),
    # which turns spaces into '+'. `quote_plus` matches that behavior.
    return quote_plus(str(val), safe="")


class VnpayService:
    @staticmethod
    def generate_txn_ref() -> str:
        # VNPay typically expects a string without spaces; keep it short.
        return uuid.uuid4().hex[:32]

    @staticmethod
    def build_hash_data(params: dict[str, Any]) -> str:
        # Sort keys alphabetically and concatenate as key=value&key=value...
        items = []
        for k in sorted(params.keys()):
            if params[k] is None:
                continue
            items.append(f"{_quote(k)}={_quote(params[k])}")
        return "&".join(items)

    @staticmethod
    def sign_request(hash_secret: str, params: dict[str, Any]) -> str:
        hash_data = VnpayService.build_hash_data(params)
        # VNPay v2.1.0 supports HMACSHA512
        return hmac.new(hash_secret.encode("utf-8"), hash_data.encode("utf-8"), hashlib.sha512).hexdigest()

    @staticmethod
    def create_payment_url(
        *,
        payment_url: str,
        tmn_code: str,
        hash_secret: str,
        return_url: str,
        ip_addr: str,
        locale: str,
        curr_code: str,
        order_type: str,
        txn_ref: str,
        amount_vnd: int,
        order_info: str,
        version: str = "2.1.0",
        create_date: str | None = None,
        expire_date: str | None = None,
    ) -> str:
        if create_date is None:
            create_date = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        if expire_date is None:
            expire_date = (datetime.utcnow() + timedelta(minutes=5000)).strftime("%Y%m%d%H%M%S")

        # Map fields following VNPay paymentv2/vpcpay.html reference.
        vnp_params: dict[str, Any] = {
            "vnp_Version": version,
            "vnp_Command": "pay",
            "vnp_TmnCode": tmn_code,
            "vnp_Amount": int(amount_vnd) * 100,
            "vnp_CurrCode": curr_code,
            "vnp_TxnRef": txn_ref,
            "vnp_OrderInfo": order_info,
            "vnp_OrderType": order_type,
            "vnp_Locale": locale,
            "vnp_ReturnUrl": "http://localhost:3000/payment-result",
            "vnp_IpAddr": "1.1.1.1",
            "vnp_CreateDate": create_date,
            "vnp_ExpireDate": expire_date,
        }

        secure_hash = VnpayService.sign_request(hash_secret, vnp_params)
        vnp_params["vnp_SecureHash"] = secure_hash

        query = "&".join(
            [f"{_quote(k)}={_quote(v)}" for k, v in sorted(vnp_params.items()) if v is not None]
        )
        print(f"{payment_url}?{query}")
        return f"{payment_url}?{query}"

    @staticmethod
    def verify_return(
        *,
        hash_secret: str,
        vnp_params: dict[str, Any],
        provided_secure_hash: str,
    ) -> bool:
        # Remove secure hash fields before recalculating
        params = dict(vnp_params)
        params.pop("vnp_SecureHash", None)
        params.pop("vnp_SecureHashType", None)
        expected = VnpayService.sign_request(hash_secret, params)
        return expected.lower() == (provided_secure_hash or "").lower()

