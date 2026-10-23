"""A CLI can't silently create extra superadmins or reuse seller identities."""
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.bootstrap import BootstrapError, provision_first_superadmin
from app.models import AuditEvent, Base, User


@pytest.fixture
def db():
    engine=create_engine("sqlite+pysqlite://",connect_args={"check_same_thread":False},
                         poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_bootstrap_requires_identity_and_uses_no_password(db):
    with pytest.raises(BootstrapError):
        provision_first_superadmin(db,"  ","Admin")
    with pytest.raises(BootstrapError):
        provision_first_superadmin(db,"sub-1"," ")
    assert db.scalar(select(User)) is None


def test_bootstrap_creates_first_superadmin_and_audit_once(db):
    user=provision_first_superadmin(db,"sub-from-trusted-oidc-provider","Gestão UMA")
    assert user.is_superadmin
    assert user.profile=="administrator"
    assert user.active
    assert not hasattr(user,"password")
    assert db.scalar(select(User)).auth_subject=="sub-from-trusted-oidc-provider"
    event=db.scalar(select(AuditEvent))
    assert event.action=="security.superadmin.bootstrapped"
    assert event.actor_id==user.id
    with pytest.raises(BootstrapError):
        provision_first_superadmin(db,"another-sub","Pessoa B")
    assert len(db.scalars(select(User)).all())==1


def test_bootstrap_rejects_existing_account_without_promoting(db):
    existing=User(id=uuid4(),auth_subject="seller-oidc",
                  display_name="Sales",profile="seller",is_superadmin=False,active=True)
    db.add(existing);db.commit()
    with pytest.raises(BootstrapError):
        provision_first_superadmin(db,"seller-oidc","Admin")
    actual=db.scalar(select(User))
    assert actual.is_superadmin is False
    assert actual.profile=="seller"
