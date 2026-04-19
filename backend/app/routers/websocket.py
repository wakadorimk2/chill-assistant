"""
WebSocketルーター

WebSocket接続とリアルタイム通信を管理するエンドポイント
"""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..ws.manager import manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    WebSocketエンドポイント
    クライアントとのリアルタイム通信を確立する
    """
    await manager.connect(websocket)
    try:
        await manager.send_personal_message(
            {"type": "system", "data": {"message": "WebSocket接続が確立されました。"}},
            websocket,
        )

        await manager.send_personal_message(
            {"type": "status", "data": {"server_status": "running"}},
            websocket,
        )

        while True:
            data = await websocket.receive_json()
            message_type = data.get("type", "unknown")

            if message_type == "ping":
                await manager.send_personal_message(
                    {"type": "pong", "data": {"timestamp": data.get("timestamp", 0)}},
                    websocket,
                )
            elif message_type == "command":
                command = data.get("command", "")
                if command == "status":
                    await manager.send_personal_message(
                        {"type": "status", "data": {"server_status": "running"}},
                        websocket,
                    )
                else:
                    logger.debug(f"未対応のコマンド: {command}")

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("WebSocket接続が切断されました")
    except Exception as e:
        logger.error(f"WebSocket処理中のエラー: {str(e)}")
        manager.disconnect(websocket)
