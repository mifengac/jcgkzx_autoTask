from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
from typing import Any

from fastapi import HTTPException, status

from autotask_api.config import get_settings


settings = get_settings()
_oracle_client_lock = threading.Lock()
_oracle_client_initialized = False
_REQUIRED_CLIENT_LIBS = (
    "libclntsh.so.11.1",
    "libnnz11.so",
    "libocci.so.11.1",
    "libociei.so",
)


@dataclass(frozen=True)
class SmsGatewayCredentials:
    userid: str
    password: str
    userport: str


class OracleSmsGateway:
    provider_name = "oracle_dfsdl"

    def __init__(self) -> None:
        self._ensure_oracle_client()

    def _ensure_oracle_client(self) -> None:
        global _oracle_client_initialized
        if _oracle_client_initialized:
            return

        if not settings.oracle_thick_mode:
            return
        if not settings.oracle_client_lib_dir:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Oracle 11g must use python-oracledb thick mode. "
                    "Set ORACLE_CLIENT_LIB_DIR to instantclient_11_2."
                ),
            )

        client_dir = Path(settings.oracle_client_lib_dir)
        missing_libs = [name for name in _REQUIRED_CLIENT_LIBS if not (client_dir / name).exists()]
        if missing_libs:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Oracle Instant Client directory is incomplete: "
                    + ", ".join(missing_libs)
                ),
            )

        with _oracle_client_lock:
            if _oracle_client_initialized:
                return
            import oracledb

            try:
                oracledb.init_oracle_client(lib_dir=str(client_dir))
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to initialize Oracle thick client: {exc}",
                ) from exc
            _oracle_client_initialized = True

    def _connect(self):
        if not settings.oracle_dsn or not settings.oracle_user or not settings.oracle_password:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Oracle connection settings are incomplete.",
            )

        import oracledb

        try:
            return oracledb.connect(
                user=settings.oracle_user,
                password=settings.oracle_password,
                dsn=settings.oracle_dsn,
            )
        except Exception as exc:
            message = str(exc)
            if "not supported by python-oracledb in thin mode" in message:
                message = (
                    "Oracle 11g requires thick mode. "
                    "Set ORACLE_CLIENT_LIB_DIR to instantclient_11_2."
                )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to connect Oracle SMS database: {message}",
            ) from exc

    def resolve_credentials(self, runtime_config: dict[str, Any]) -> SmsGatewayCredentials:
        sms_userid = str(runtime_config.get("sms_userid") or settings.sms_userid or "").strip()
        sms_password = str(runtime_config.get("sms_password") or settings.sms_password or "").strip()

        userport = str(runtime_config.get("sms_userport") or "").strip()
        if not userport:
            business_name = str(runtime_config.get("sms_business_name") or "").strip()
            if business_name:
                userport = settings.sms_business_ports.get(business_name, "")
        if not userport:
            userport = str(settings.sms_userport or "").strip()

        if not sms_userid or not sms_password or not userport:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="SMS gateway credentials are incomplete.",
            )
        return SmsGatewayCredentials(userid=sms_userid, password=sms_password, userport=userport)

    def check_duplicate(self, *, eid: str, mobile: str) -> bool:
        sql = """
            SELECT COUNT(*)
            FROM yfgadb.dfsdl
            WHERE eid = :eid
              AND mobile = :mobile
        """
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, {"eid": eid, "mobile": mobile})
                count = cur.fetchone()[0]
                return int(count or 0) > 0
        finally:
            conn.close()

    def enqueue_sms(
        self,
        *,
        mobile: str,
        content: str,
        eid: str,
        credentials: SmsGatewayCredentials,
    ) -> None:
        sql = """
            INSERT INTO yfgadb.dfsdl(
                id, mobile, content, deadtime, status, eid,
                userid, password, userport
            ) VALUES (
                yfgadb.seq_sendsms.nextval,
                :mobile, :content, SYSDATE, '0', :eid,
                :sms_userid, :sms_password, :sms_userport
            )
        """
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    {
                        "mobile": mobile,
                        "content": content,
                        "eid": eid,
                        "sms_userid": credentials.userid,
                        "sms_password": credentials.password,
                        "sms_userport": credentials.userport,
                    },
                )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to enqueue SMS into Oracle: {exc}",
            ) from exc
        finally:
            conn.close()
