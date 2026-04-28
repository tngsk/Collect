実行と操作手順
起動: Pi 5 のターミナルで uvicorn main:app --host 0.0.0.0 --port 8000 を実行します。

アクセス: 参加者はスマホで http://[PiのIP]:8000 にアクセスし、スクリーン用PCは http://[PiのIP]:8000/screen にアクセスします。

フェーズの進行（実験者）: 別のターミナルからAPIを叩いて進行します。

curl -X POST http://127.0.0.1:8000/control/phase/EVALUATE （回答画面表示）

curl -X POST http://127.0.0.1:8000/control/phase/WAITING （待機画面に戻す）
