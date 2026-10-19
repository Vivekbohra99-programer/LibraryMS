"""Tests for Member management and profiles."""
from app.models.member import Member


def test_member_list_staff(librarian_client):
    response = librarian_client.get('/members')
    assert response.status_code == 200
    assert b'Test Member' in response.data


def test_add_member_staff(librarian_client, app):
    response = librarian_client.post('/members/add', data={
        'name': 'Grace Hopper',
        'email': 'grace@navy.mil',
        'phone': '555-4321',
        'address': 'Arlington, VA',
        'status': 'active',
        'loan_limit': 6,
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'added' in response.data

    with app.app_context():
        m = Member.query.filter_by(email='grace@navy.mil').first()
        assert m is not None
        assert m.name == 'Grace Hopper'
        assert m.loan_limit == 6


def test_edit_member_status(librarian_client, app):
    with app.app_context():
        m = Member.query.first()
        m_id = m.id

    response = librarian_client.post(f'/members/{m_id}/edit', data={
        'name': 'Test Member Updated',
        'email': 'member@test.com',
        'phone': '555-1234',
        'address': 'New Address',
        'status': 'suspended',
        'loan_limit': 3,
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'updated' in response.data

    with app.app_context():
        m = Member.query.get(m_id)
        assert m.status == 'suspended'
        assert not m.is_active


def test_member_profile_page(member_client):
    response = member_client.get('/profile', follow_redirects=True)
    assert response.status_code == 200
    assert b'Test Member' in response.data
    assert b'member@test.com' in response.data
