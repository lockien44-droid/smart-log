from app.server import app, socketio

socketio.run(
    app,
    host="0.0.0.0",
    port=8000,
    debug=False,
    use_reloader=False,
    allow_unsafe_werkzeug=True,
)
