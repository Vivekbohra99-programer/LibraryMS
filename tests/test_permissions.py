"""Tests for permissions, role-based access control, and error handling."""


def test_unauthenticated_cannot_access_admin(client):
    response = client.get('/admin/performance')
    # Should redirect to login
    assert response.status_code == 302
    assert '/login' in response.headers.get('Location', '')


def test_member_cannot_access_admin(member_client):
    response = member_client.get('/admin/performance')
    assert response.status_code == 403


def test_member_cannot_access_staff_issue(member_client):
    response = member_client.get('/transactions/issue')
    assert response.status_code == 403


def test_admin_can_access_admin_performance(admin_client):
    response = admin_client.get('/admin/performance')
    assert response.status_code == 200
    assert b'Q17 Performance' in response.data or b'Performance' in response.data


def test_librarian_can_access_books_management(librarian_client):
    response = librarian_client.get('/books')
    assert response.status_code == 200
    assert b'Book Management' in response.data or b'Books' in response.data


def test_404_error_page(client):
    response = client.get('/nonexistent-page-url-12345')
    assert response.status_code == 404
    assert b'404' in response.data


def test_console_requires_login(client):
    response = client.get('/admin/performance/console')
    assert response.status_code == 302
    assert '/login' in response.headers.get('Location', '')


def test_member_cannot_open_console(member_client):
    assert member_client.get('/admin/performance/console').status_code == 403


def test_admin_console_renders_real_report(admin_client):
    response = admin_client.get('/admin/performance/console')
    assert response.status_code == 200
    assert b'Performance console' in response.data
    assert b'data-value=' in response.data          # gauges are fed from the report
    assert b'csrf_token' in response.data           # benchmark key is a real POST form
