# coding=utf-8
"""A collection of model factories using factory boy."""
import factory  # factory boy
from aot-ai.aot-ai_flask.extensions import db
from aot-ai.databases import models
from faker import Faker


faker = Faker()


class UserFactory(factory.alchemy.SQLAlchemyModelFactory):
    """A factory for creating user models."""
    class Meta(object):
        model = models.User
        sqlalchemy_session = db.session

    name = faker.name()
    email = faker.email()
