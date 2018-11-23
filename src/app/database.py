# coding: utf8
from __future__ import unicode_literals

import peewee as orm
from pathlib import Path
import ujson

from prodigy.util import PRODIGY_HOME, TASK_HASH_ATTR, INPUT_HASH_ATTR, log
from prodigy.util import get_config, get_entry_points, convert_blob, get_display_name


DB_PROXY = orm.Proxy()
_DB = None


def get_db():
    """Get access to the shared database instance that was previously connected"""
    global _DB
    return _DB


def disconnect():
    """Disconnect the shared database instance and revert it back to None type"""
    global _DB
    if _DB is None:
        raise AssertionError("Database is already destroyed")
    _DB.close()
    _DB = None


def connect(db_id=None, db_settings=None):
    """Connect to the database.

    db_id (unicode): 'sqlite' (default), 'postgresql' or 'mysql'.
    db_settings (dict): Optional database connection parameters.
    RETURNS (prodigy.components.db.Database): The initialized database.
    """
    global _DB
    if _DB is not None:
        return _DB
    connectors = {'sqlite': connect_sqlite, 'postgresql': connect_postgresql,
                  'mysql': connect_mysql}
    user_dbs = get_entry_points('prodigy_db')
    if user_dbs:
        log("DB: Added {} connector(s) via entry points".format(len(user_dbs)))
    if db_id in user_dbs:
        _DB = user_dbs[db_id]
        return _DB
    config = get_config()
    if db_id in (True, False, None):
        db_id = config.get('db', 'sqlite')
    if db_settings in (True, False, None):
        config_db_settings = config.setdefault('db_settings', {})
        db_settings = config_db_settings.get(db_id, {})
    if db_id not in connectors:
        raise ValueError("Invalid database id: {}".format(db_id))
    db_name, db = connectors[db_id](**db_settings)
    _DB = Database(db, db_id, db_name)
    log("DB: Connecting to database {}".format(db_name), db_settings)
    return _DB


class BaseModel(orm.Model):
    class Meta:
        database = DB_PROXY


class Dataset(BaseModel):
    name = orm.CharField(unique=True)
    created = orm.TimestampField()
    meta = orm.BlobField()
    session = orm.BooleanField()


class Example(BaseModel):
    input_hash = orm.BigIntegerField()
    task_hash = orm.BigIntegerField()
    content = orm.BlobField()

    def load(self):
        content = convert_blob(self.content)
        return ujson.loads(content)


class Link(BaseModel):
    example = orm.ForeignKeyField(Example)
    dataset = orm.ForeignKeyField(Dataset)


class User(BaseModel):
    username = orm.CharField(unique=True)
    password = orm.CharField()
    email = orm.CharField()


def connect_sqlite(**settings):
    database = settings.pop('name', 'prodigy.db')
    path = settings.pop('path', PRODIGY_HOME)
    if database != ':memory:':
        database = str(Path(path) / database)
    return 'SQLite', orm.SqliteDatabase(database, **settings)


def connect_postgresql(**settings):
    database = 'prodigy'
    for setting in ('db', 'name', 'dbname', 'database'):
        if setting in settings:
            database = settings.pop(setting)
    return 'PostgreSQL', orm.PostgresqlDatabase(database, **settings)


def connect_mysql(**settings):
    database = 'prodigy'
    for setting in ('db', 'name', 'dbname', 'database'):
        if setting in settings:
            database = settings.pop(setting)
    return 'MySQL', orm.MySQLDatabase(database, **settings)


class Database(object):
    def __init__(self, db, display_id='custom', display_name=None):
        """Initialize a database.

        db: A database object that can be initialized by peewee.
        display_id (unicode): Database ID used for logging, e.g. 'sqlite'.
        display_name (unicode): Database name used for logging, e.g. 'SQLite'.
        RETURNS (Database): The initialized database.
        """
        DB_PROXY.initialize(db)
        self.db_id = display_id
        self.db_name = display_name or get_display_name(db)
        log("DB: Initialising database {}".format(self.db_name))
        try:
            DB_PROXY.create_tables([User, Dataset, Example, Link], safe=True)
        except orm.OperationalError:
            pass
        self.db = DB_PROXY

    def __bool__(self):
        return True

    def __len__(self):
        """
        RETURNS (int): The number of datasets in the database.
        """
        return len(self.datasets)

    def __contains__(self, name):
        """
        name (unicode): Name of the dataset.
        RETURNS (bool): Whether the dataset exists in the database.
        """
        try:
            has_ds = bool(Dataset.get(Dataset.name == name))
        except Dataset.DoesNotExist:
            has_ds = False
        return has_ds

    @property
    def datasets(self):
        """
        RETURNS (list): A list of dataset IDs.
        """
        datasets = (Dataset.select(Dataset.name)
                           .where(Dataset.session == False)  # noqa: E712
                           .order_by(Dataset.created))
        return [ds.name for ds in datasets]

    @property
    def sessions(self):
        """
        RETURNS (list): A list of session dataset IDs.
        """
        datasets = (Dataset.select(Dataset.name)
                           .where(Dataset.session == True)  # noqa: E712
                           .order_by(Dataset.created))
        return [ds.name for ds in datasets]

    def close(self):
        """
        Close the database connection (if not already closed). Called after
        API requests to avoid timeout issues, especially with MySQL.
        """
        if not self.db.is_closed():
            self.db.close()

    def reconnect(self):
        """
        Reconnect to the database. Called on API requests to avoid timeout
        issues, especiallly with MySQL. If the database connection is still
        open, it will be closed before reconnecting.
        """
        if not self.db.is_closed():
            self.db.close()
        self.db.connect()

    def get_examples(self, ids, by='task_hash'):
        """
        ids (list): List of example hashes.
        by (unicode): ID to get examples by. Defaults to 'task_hash'.
        RETURNS (list): The examples.
        """
        try:
            ids = list(ids)
        except TypeError:
            ids = [ids]
        field = getattr(Example, by)
        ids = list(ids)
        return [eg.load() for eg in Example.select().where(field << ids)]

    def get_meta(self, name):
        """
        name (unicode): The dataset name.
        RETURNS (dict): The dataset meta.
        """
        if name not in self:
            return None
        dataset = Dataset.get(Dataset.name == name)
        meta = convert_blob(dataset.meta)
        meta = ujson.loads(meta)
        meta['created'] = dataset.created
        return meta

    def get_dataset(self, name, default=None):
        """
        name (unicode): The dataset name.
        default: Return value if dataset not in database.
        RETURNS (list): The examples in the dataset or default value.
        """
        if name not in self:
            return default
        dataset = Dataset.get(Dataset.name == name)
        examples = (Example
                    .select()
                    .join(Link)
                    .join(Dataset)
                    .where(Dataset.id == dataset.id)).execute()
        log("DB: Loading dataset '{}' ({} examples)"
            .format(name, len(examples)))
        return [eg.load() for eg in examples]

    def get_input_hashes(self, *names):
        """
        *names (unicode): Dataset names to get hashes for.
        RETURNS (set): The input hashes.
        """
        datasets = Dataset.select(Dataset.id).where(Dataset.name << names)
        examples = (Example
                    .select(Example.input_hash)
                    .join(Link)
                    .join(Dataset)
                    .where(Dataset.id << datasets)).execute()
        return set([eg.input_hash for eg in examples])

    def get_task_hashes(self, *names):
        """
        *names (unicode): The dataset names.
        RETURNS (set): The task hashes.
        """
        datasets = Dataset.select(Dataset.id).where(Dataset.name << names)
        examples = (Example
                    .select(Example.task_hash)
                    .join(Link)
                    .join(Dataset)
                    .where(Dataset.id << datasets)).execute()
        return set([eg.task_hash for eg in examples])

    def add_dataset(self, name, meta={}, session=False):
        """
        name (unicode): The name of the dataset to add.
        meta (dict): Optional dataset meta.
        session (bool): Whether the dataset is a session dataset.
        RETURNS (list): The created dataset.
        """
        if any([char in name for char in (',', ' ')]):
            raise ValueError("Dataset name can't include commas or whitespace")
        try:
            dataset = Dataset.get(Dataset.name == name)
            log("DB: Getting dataset '{}'".format(name))
        except Dataset.DoesNotExist:
            log("DB: Creating dataset '{}'".format(name), meta)
            meta = ujson.dumps(meta, escape_forward_slashes=False)
            dataset = Dataset.create(name=name, meta=meta, session=session)
        return dataset

    def add_examples(self, examples, datasets=tuple()):
        """
        examples (list): The examples to add.
        datasets (list): The names of the dataset(s) to add the examples to.
        """
        with self.db.atomic():
            ids = []
            for eg in examples:
                content = ujson.dumps(eg, escape_forward_slashes=False)
                eg = Example.create(input_hash=eg[INPUT_HASH_ATTR],
                                    task_hash=eg[TASK_HASH_ATTR],
                                    content=content)
                ids.append(eg.id)
        if type(datasets) is not tuple and type(datasets) is not list:
            raise ValueError('datasets must be a tuple or list type, not: {}'.format(type(datasets)))
        for dataset in datasets:
            self.link(dataset, ids)
        log("DB: Added {} examples to {} datasets"
            .format(len(examples), len(datasets)))

    def link(self, dataset_name, example_ids):
        """
        dataset_name (unicode): The name of the dataset.
        example_ids (list): The IDs of the examples to link to the dataset.
        """
        with self.db.atomic():
            dataset = self.add_dataset(dataset_name)
            for eg in example_ids:
                link = Link.create(dataset=dataset.id, example=eg)  # noqa F841

    def unlink(self, dataset):
        """
        dataset (unicode): The name of the dataset to unlink.
        """
        dataset = Dataset.get(Dataset.name == dataset)
        query = Link.delete().where(Dataset.id == dataset.id)
        query.execute()

    def drop_dataset(self, name):
        """
        name (unicode): The name of the dataset to drop.
        RETURNS (bool): True if dataset was dropped.
        """
        dataset = Dataset.get(Dataset.name == name)
        query = Link.delete().where(Link.dataset == dataset.id)
        query.execute()
        query = Dataset.delete().where(Dataset.id == dataset.id)
        query.execute()
        self.db.commit()
        log("DB: Removed dataset '{}'".format(name))
        return True

    def drop_examples(self, ids, by='task_hash'):
        """
        ids (list): The IDs of the examples to drop.
        by (unicode): ID to get examples by. Defaults to 'task_hash'.
        """
        try:
            ids = list(ids)
        except TypeError:
            ids = [ids]
        field = getattr(Example, by)
        ids = list(ids)
        query = Example.delete().where(field << ids)
        query.execute()
        self.db.commit()

    def save(self):
        log("DB: Saving database")
        self.reconnect()
        self.db.commit()

