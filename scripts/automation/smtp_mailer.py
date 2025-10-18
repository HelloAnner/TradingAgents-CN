#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SMTP 邮件发送工具

支持：
- SSL/STARTTLS（基于配置）
- 多收件人
- 附件（用于发送 PDF 报告）

配置字段（MailConfig）：
{
  "host": "smtp.example.com",
  "port": 465,
  "username": "user@example.com",
  "password": "***",
  "use_ssl": true,
  "use_tls": false,
  "from_email": "noreply@example.com",
  "from_name": "TradingAgents-CN"
}
"""

from __future__ import annotations

import os
import ssl
import smtplib
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import mimetypes
from typing import List, Optional, Dict, Any
from email.header import Header
from email.utils import formataddr

from tradingagents.utils.logging_manager import get_logger


logger = get_logger("automation.mailer")


@dataclass
class MailConfig:
    host: str = ""
    port: int = 465
    username: str = ""
    password: str = ""
    use_ssl: bool = True
    use_tls: bool = False
    from_email: str = ""
    from_name: str = "TradingAgents-CN"

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MailConfig":
        return cls(
            host=str(d.get("host", "")),
            port=int(d.get("port", 465)),
            username=str(d.get("username", "")),
            password=str(d.get("password", "")),
            use_ssl=bool(d.get("use_ssl", True)),
            use_tls=bool(d.get("use_tls", False)),
            from_email=str(d.get("from_email", "")),
            from_name=str(d.get("from_name", "TradingAgents-CN")),
        )


class MailSender:
    def __init__(self, config: MailConfig) -> None:
        self.cfg = config

    def _connect(self) -> smtplib.SMTP:
        host, port = self.cfg.host, self.cfg.port
        if not host or not port:
            raise ValueError("SMTP 主机或端口未配置")

        # 首选 SSL 方式
        try:
            if self.cfg.use_ssl:
                context = ssl.create_default_context()
                server = smtplib.SMTP_SSL(host, port, context=context, timeout=30)
            else:
                server = smtplib.SMTP(host, port, timeout=30)
                if self.cfg.use_tls:
                    server.starttls(context=ssl.create_default_context())
            if self.cfg.username:
                server.login(self.cfg.username, self.cfg.password)
            return server
        except Exception as e:
            logger.warning(f"⚠️ SSL/端口 {host}:{port} 连接失败，尝试STARTTLS 587：{e}")
            # Fallback: 常见 587/TLS
            try:
                server = smtplib.SMTP(host, 587, timeout=30)
                server.starttls(context=ssl.create_default_context())
                if self.cfg.username:
                    server.login(self.cfg.username, self.cfg.password)
                return server
            except Exception as e2:
                logger.error(f"❌ SMTP 连接失败: {e2}")
                raise

    def send_email(
        self,
        to_addrs: List[str],
        subject: str,
        body: str,
        attachments: Optional[List[str]] = None,
        subtype: str = "plain",  # 兼容旧参数（忽略，始终发送 alternative）
        charset: str = "utf-8",
    ) -> None:
        if not to_addrs:
            logger.warning("未提供收件人，跳过发送")
            return

        # 顶层使用 mixed，以便附加文件；正文使用 alternative（plain + html）
        msg = MIMEMultipart('mixed')
        from_name = self.cfg.from_name or "TradingAgents-CN"
        from_email = self.cfg.from_email or self.cfg.username
        # 处理非ASCII发件人名
        try:
            from_formatted = formataddr((str(Header(from_name, charset)), from_email))
        except Exception:
            from_formatted = f"{from_name} <{from_email}>"
        msg["From"] = from_formatted
        msg["To"] = ", ".join(to_addrs)
        try:
            msg["Subject"] = str(Header(subject, charset))
        except Exception:
            msg["Subject"] = subject

        # 渲染正文（plain + html）。优先将 Markdown 转为 HTML；若失败，则用简单换行转 <br/>
        alt = MIMEMultipart('alternative')
        # 纯文本版本（回退，便于各客户端可读）
        alt.attach(MIMEText(body or "", 'plain', charset))
        # HTML 版本（Markdown 渲染）
        html_body = None
        try:
            try:
                import markdown as _md
                html_body = _md.markdown(body or "", extensions=['extra', 'sane_lists'])
            except Exception:
                html_body = None
            if not html_body:
                # 简单回退：保留换行
                safe = (body or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                html_body = f"<div style=\"white-space:pre-wrap; font-family:Arial,Helvetica,\'Microsoft YaHei\',sans-serif;\">{safe}</div>"
        except Exception:
            html_body = f"<pre>{body or ''}</pre>"
        alt.attach(MIMEText(html_body, 'html', charset))
        msg.attach(alt)

        # 附件
        for path in attachments or []:
            if not path or not os.path.exists(path):
                logger.warning(f"附件不存在，跳过: {path}")
                continue
            ctype, encoding = mimetypes.guess_type(path)
            if ctype is None or encoding is not None:
                ctype = 'application/octet-stream'
            maintype, subtype = ctype.split('/', 1)
            with open(path, 'rb') as f:
                payload = f.read()
            part = MIMEBase(maintype, subtype)
            part.set_payload(payload)
            encoders.encode_base64(part)
            filename = os.path.basename(path)
            part.add_header("Content-Disposition", f"attachment; filename=\"{filename}\"")
            msg.attach(part)

        # 发送（避免使用with上下文，部分服务器在QUIT时会异常，但邮件已成功发送）
        server = None
        try:
            server = self._connect()
            result = server.sendmail(from_email, to_addrs, msg.as_string())
            if isinstance(result, dict) and result:
                # 有收件人被拒绝
                logger.error(f"部分收件人被拒绝: {result}")
                raise RuntimeError(f"部分收件人被拒绝: {result}")
            logger.info(f"邮件已发送: {subject} -> {len(to_addrs)} 收件人")
        except Exception as e:
            logger.error(f"发送邮件失败: {e}")
            raise
        finally:
            if server is not None:
                try:
                    server.quit()
                except Exception as e:
                    # 常见：服务器提前关闭连接，忽略此类错误，不影响发送成功
                    logger.warning(f"SMTP 关闭连接时异常（已忽略，不影响发送）: {e}")
