from datetime import datetime, timedelta, timezone

from jose import jwt

from mysite.api.auth import create_access_token, create_refresh_token, verify_password
from mysite.config import ALGORITHM, SECRET_KEY
from mysite.db.models import RefreshToken, UserProfile, UserRole

REGISTER_DATA = {
    'username': 'newuser',
    'email': 'newuser@test.kg',
    'phone_number': '+996700111222',
    'password': 'password123',
}


def login(client, username, password='pass12345'):
    return client.post('/auth/login', json={'username': username, 'password': password})


def expired_token(user_db, token_type):
    payload = {
        'sub': user_db.username,
        'user_id': user_db.id,
        'type': token_type,
        'exp': datetime.now(timezone.utc) - timedelta(minutes=1),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# ---------- register ----------


def test_register_ok(client, db):
    response = client.post('/auth/register', json=REGISTER_DATA)
    assert response.status_code == 200
    data = response.json()
    assert data['role'] == 'client'
    assert data['is_active'] is True
    assert 'password' not in data
    user_db = db.query(UserProfile).filter(UserProfile.username == 'newuser').one()
    assert user_db.password != REGISTER_DATA['password']
    assert user_db.password.startswith('$2')
    assert verify_password(REGISTER_DATA['password'], user_db.password)


def test_register_ignores_role_admin(client, db):
    response = client.post(
        '/auth/register', json={**REGISTER_DATA, 'role': 'admin', 'is_active': False, 'discount_limit': '50'}
    )
    assert response.status_code == 200
    assert response.json()['role'] == 'client'
    user_db = db.query(UserProfile).filter(UserProfile.username == 'newuser').one()
    assert user_db.role == UserRole.client
    assert user_db.is_active is True
    assert user_db.discount_limit == 0


def test_register_duplicate_username_409(client, client_user):
    response = client.post('/auth/register', json={**REGISTER_DATA, 'username': client_user.username})
    assert response.status_code == 409


def test_register_duplicate_email_409(client, client_user):
    response = client.post('/auth/register', json={**REGISTER_DATA, 'email': client_user.email})
    assert response.status_code == 409


def test_register_invalid_phone_422(client):
    response = client.post('/auth/register', json={**REGISTER_DATA, 'phone_number': '0700111222'})
    assert response.status_code == 422


def test_register_short_password_422(client):
    response = client.post('/auth/register', json={**REGISTER_DATA, 'password': '1234567'})
    assert response.status_code == 422


def test_register_invalid_email_422(client):
    response = client.post('/auth/register', json={**REGISTER_DATA, 'email': 'not-an-email'})
    assert response.status_code == 422


# ---------- login ----------


def test_login_ok(client, db, client_user):
    response = login(client, client_user.username)
    assert response.status_code == 200
    data = response.json()
    assert data['type'] == 'bearer'
    assert data['user_id'] == client_user.id
    assert data['access_token']
    assert data['refresh_token']
    assert 'password' not in data
    assert db.query(RefreshToken).filter(RefreshToken.token == data['refresh_token']).count() == 1


def test_login_twice_creates_distinct_refresh_tokens(client, db, client_user):
    first = login(client, client_user.username)
    second = login(client, client_user.username)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()['refresh_token'] != second.json()['refresh_token']
    assert db.query(RefreshToken).filter(RefreshToken.user_id == client_user.id).count() == 2


def test_login_wrong_password_401(client, client_user):
    assert login(client, client_user.username, 'wrong-password').status_code == 401


def test_login_unknown_user_401(client):
    assert login(client, 'nobody').status_code == 401


def test_login_errors_have_same_text(client, client_user):
    wrong_password = login(client, client_user.username, 'wrong-password')
    unknown_user = login(client, 'nobody')
    assert wrong_password.json() == unknown_user.json()


def test_login_blocked_user_403(client, make_user):
    user_db = make_user('blocked', is_active=False)
    assert login(client, user_db.username).status_code == 403


def test_login_blocked_user_wrong_password_401(client, make_user):
    user_db = make_user('blocked', is_active=False)
    assert login(client, user_db.username, 'wrong-password').status_code == 401


# ---------- access_generate ----------


def test_access_generate_ok(client, db, client_user):
    old_refresh = login(client, client_user.username).json()['refresh_token']
    response = client.post('/auth/access_generate', json={'refresh_token': old_refresh})
    assert response.status_code == 200
    data = response.json()
    assert data['access_token']
    assert data['refresh_token'] != old_refresh
    assert data['user_id'] == client_user.id
    assert db.query(RefreshToken).filter(RefreshToken.token == old_refresh).count() == 0
    assert db.query(RefreshToken).filter(RefreshToken.token == data['refresh_token']).count() == 1


def test_access_generate_new_access_works(client, client_user):
    old_refresh = login(client, client_user.username).json()['refresh_token']
    data = client.post('/auth/access_generate', json={'refresh_token': old_refresh}).json()
    response = client.get('/user/profile', headers={'Authorization': f'Bearer {data["access_token"]}'})
    assert response.status_code == 200


def test_access_generate_old_refresh_after_rotation_401(client, client_user):
    old_refresh = login(client, client_user.username).json()['refresh_token']
    assert client.post('/auth/access_generate', json={'refresh_token': old_refresh}).status_code == 200
    response = client.post('/auth/access_generate', json={'refresh_token': old_refresh})
    assert response.status_code == 401


def test_access_generate_with_access_token_401(client, client_user):
    access = login(client, client_user.username).json()['access_token']
    response = client.post('/auth/access_generate', json={'refresh_token': access})
    assert response.status_code == 401


def test_access_generate_expired_refresh_401(client, db, client_user):
    token = expired_token(client_user, 'refresh')
    db.add(RefreshToken(user_id=client_user.id, token=token))
    db.commit()
    response = client.post('/auth/access_generate', json={'refresh_token': token})
    assert response.status_code == 401


def test_access_generate_garbage_token_401(client):
    response = client.post('/auth/access_generate', json={'refresh_token': 'garbage.token.value'})
    assert response.status_code == 401


def test_access_generate_valid_jwt_not_in_db_401(client, client_user):
    token = create_refresh_token({'sub': client_user.username, 'user_id': client_user.id})
    response = client.post('/auth/access_generate', json={'refresh_token': token})
    assert response.status_code == 401


def test_access_generate_blocked_user_401(client, db, client_user):
    refresh = login(client, client_user.username).json()['refresh_token']
    client_user.is_active = False
    db.commit()
    response = client.post('/auth/access_generate', json={'refresh_token': refresh})
    assert response.status_code == 401


# ---------- logout ----------


def test_logout_ok(client, db, client_user):
    refresh = login(client, client_user.username).json()['refresh_token']
    response = client.post('/auth/logout', json={'refresh_token': refresh})
    assert response.status_code == 200
    assert db.query(RefreshToken).filter(RefreshToken.token == refresh).count() == 0
    assert client.post('/auth/access_generate', json={'refresh_token': refresh}).status_code == 401


def test_logout_unknown_token_401(client, client_user):
    token = create_refresh_token({'sub': client_user.username, 'user_id': client_user.id})
    response = client.post('/auth/logout', json={'refresh_token': token})
    assert response.status_code == 401


def test_logout_with_access_token_401(client, client_user):
    access = login(client, client_user.username).json()['access_token']
    response = client.post('/auth/logout', json={'refresh_token': access})
    assert response.status_code == 401


# ---------- защищенные эндпоинты ----------


def test_protected_without_token_401(client):
    assert client.get('/user/profile').status_code == 401


def test_protected_with_refresh_token_as_access_401(client, client_user):
    refresh = login(client, client_user.username).json()['refresh_token']
    response = client.get('/user/profile', headers={'Authorization': f'Bearer {refresh}'})
    assert response.status_code == 401


def test_protected_expired_access_401(client, client_user):
    token = expired_token(client_user, 'access')
    response = client.get('/user/profile', headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 401


def test_protected_garbage_token_401(client):
    response = client.get('/user/profile', headers={'Authorization': 'Bearer garbage'})
    assert response.status_code == 401


def test_protected_blocked_user_access_401(client, db, client_user):
    access = login(client, client_user.username).json()['access_token']
    client_user.is_active = False
    db.commit()
    response = client.get('/user/profile', headers={'Authorization': f'Bearer {access}'})
    assert response.status_code == 401


def test_protected_token_without_user_id_401(client, client_user):
    token = create_access_token({'sub': client_user.username})
    response = client.get('/user/profile', headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 401
