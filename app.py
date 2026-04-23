from app import create_app

app = create_app()

if __name__ == "__main__":
    import os

    port = int(os.getenv("PORT", "3000"))
    app.run(debug=True, port=port)

