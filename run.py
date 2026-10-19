"""Entry point - run the Library Management System web application."""
import os

from app import create_app

app = create_app()

if __name__ == '__main__':
    # Debug mode shows an interactive debugger in the browser when a page crashes, which lets anyone who
    # can reach the page run code on this computer. So it is OFF unless you ask for it:
    #   Windows:  set FLASK_DEBUG=1      Linux/macOS:  export FLASK_DEBUG=1
    debug = os.environ.get('FLASK_DEBUG', '').strip().lower() in ('1', 'true', 'yes', 'on')
    app.run(debug=debug, host='127.0.0.1', port=5000)
