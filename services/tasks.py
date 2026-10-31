from dao import query_session, action_session
from dao.models import PanoramaGroup, TaskPnt
from services import BaseService


class TaskService(BaseService):

    def __init__(self):
        super(TaskService, self).__init__(PanoramaGroup, name="Task Service")


    def get_by_id(self, id):
        with query_session() as sess:
            p=sess.query(PanoramaGroup).get(id)
            return p


    def list(self):
        with query_session() as sess:
            tasks=sess.query(PanoramaGroup).all()
            return tasks

    def get_todo(self,ctype):
        with query_session() as sess:
            return sess.query(PanoramaGroup).filter(PanoramaGroup.ctype == ctype, PanoramaGroup.status == 0).first()

    def update(self,id, status):
        with action_session() as sess:
            t = sess.query(PanoramaGroup).get(id)
            t.status=status
            return t.id
        return None

class PntTaskService(BaseService):
    def __init__(self):
        super(PntTaskService, self).__init__(TaskPnt, name="Pnt Task Service")


    def get_by_id(self, id):
        with query_session() as sess:
            p=sess.query(TaskPnt).filter(TaskPnt.id == id).first()
            return p

    def get_by_name(self,batch,loc):
        with query_session() as sess:
            return sess.query(TaskPnt).filter(TaskPnt.batch == batch, TaskPnt.loc == loc).first()

    def update_status(self,id,status):
        with action_session() as sess:
            p=sess.query(TaskPnt).filter(TaskPnt.id==id).first()
            p.status=status
            return p.id
        return None

    def update_files(self,batch,loc,files):
        with action_session() as sess:
            p=sess.query(TaskPnt).filter(TaskPnt.batch==batch,TaskPnt.loc==loc).first()
            p.files=files
            return p.id
        return None

    def get_todo(self,ctype):
        with query_session() as sess:
            return sess.query(TaskPnt).filter(TaskPnt.ctype==ctype,TaskPnt.status==0).first()

    def list(self):
        with query_session() as sess:
            tasks=sess.query(TaskPnt).all()
            return tasks


if __name__ == '__main__':
    service = TaskService()
    items = service.list()
    print(len(items))
    if len(items) >1:
        print(items[0])