from assetify_app import create_app

# The app factory creates and configures the app
app = create_app()

if __name__ == '__main__':
    app.run(debug=True)