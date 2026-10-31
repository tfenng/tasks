from fastapi import FastAPI, Request

from starlette import status
from starlette.responses import JSONResponse

from config import configs
from services import task_service, pnt_task_service

app = FastAPI(
    openapi_url="/task/openapi.json",
    docs_url="/task/docs",
    arbitrary_types_allowed=True
)

SETTINGS = configs()

@app.get("/healthcheck", status_code=200)
def healthcheck():
    return {"status": "running"}


@app.exception_handler(Exception)
async def all_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error_code": 500, "message": exc.args}
    )


@app.get("/img/", summary="查询全景影像的列表", status_code=200)
def list():
    panorama_list = task_service.list()
    return {'val': panorama_list}

@app.get("/img/{ctype}/head", summary="查询1st全景影像的列表", status_code=200)
def todo(ctype:str):
    return task_service.get_todo(ctype)


@app.get("/img/{id}",summary="根据地点ID查询全景影像的详情", status_code=200)
def get(id:int):
    img_file=task_service.get_by_id(id)
    return {'val': img_file}

@app.put("/img/",summary="updated task status", status_code=200)
def put(id:int , status:int):
    ret=task_service.update(id,status)
    return {'id':ret}


@app.get("/pnt/", summary="查询PointCloud的列表", status_code=200)
def list():
    items = pnt_task_service.list()
    return {'val': items}


@app.get("/pnt/{id}",summary="根据PK查询PointCloud的详情", status_code=200)
def get(id:int):
    item=pnt_task_service.get_by_id(id)
    return {'val': item}

@app.get("/pnt/{batch}/{loc}",summary="根据PK查询PointCloud的详情", status_code=200)
def get_by_name(batch:str,loc:str):
    item=pnt_task_service.get_by_name(batch,loc)
    return {'val': item}


@app.put("/pnt/",summary="update PntTask",status_code=200)
def  put(id:int,status:int):
    if id is not None and status is not None:
        ret=pnt_task_service.update_status(id,status)
        return {'id': ret}

@app.put("/pnt/files",summary="update PntTask",status_code=200)
def  put(batch:str,loc:str,files:int):
    if batch is not None and loc is not None and files>=0:
        ret=pnt_task_service.update_files(batch,loc,files)
        return {'id': ret}



@app.get("/pnt/{ctype}/head", summary="查询1st PontCloud Task", status_code=200)
def todo(ctype:str):
    return pnt_task_service.get_todo(ctype)







