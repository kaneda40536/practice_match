"""テストで使う部品"""
from django.contrib.auth.hashers import make_password

from schools.models import School
from .models import User


def make_school(code, password=None, **fields):
    """学校アカウント（学校ID＝code）と、その学校情報を作る"""
    account = User.objects.create(
        username=code, role=User.Role.SCHOOL, password=make_password(password))
    return School.objects.create(account=account, **fields)
