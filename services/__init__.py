import math
from dao import query_session


class Pagination(object):

    def __init__(self, page, per_page, total):
        self.page = page
        self.per_page = per_page
        self.total = total

    @property
    def pages(self):
        return int(math.ceil(self.total / float(self.per_page)))

    @property
    def offset(self):
        return (self.page - 1) * self.per_page

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def has_next(self):
        return self.page < self.pages

    @property
    def dict(self):
        return {'page': self.page, 'pages': self.pages, 'per_page': self.per_page, 'total': self.total}

    def __repr__(self):
        return '<Pagination: %d/%d,%d/%d>' % (self.page, self.pages, self.per_page, self.total)


class BaseService(object):
    def __init__(self, model, name="BaseService"):
        self.name = name
        self.model = model
        self.pager = Pagination

    def condition_parser(self, args, config, model=None):
        for arg, expr in config.items():
            if arg in args:
                val = args[arg]
                if expr == "like":
                    yield getattr(model if model else self.model, arg).like(u"%{}%".format(val))
                elif expr == "eq":
                    yield getattr(model if model else self.model, arg) == val
                elif expr == "gt":
                    yield getattr(model if model else self.model, arg) > val
                elif expr == "ls":
                    yield getattr(model if model else self.model, arg) < val
                else:
                    pass

    def count(self, model=None, condition=None):
        with query_session() as session:
            filters = condition if condition else ()
            return session.query(model if model else self.model).filter(*filters).count()


from services.tasks import TaskService
from services.tasks import PntTaskService
from services.pointclouds import PointCloudService
from services.panoramas import PanoramaService

task_service = TaskService()
pnt_task_service= PntTaskService()
point_cloud_service=PointCloudService()
panorama_service=PanoramaService()