from fastapi import APIRouter, Depends
from src.config.database import database
from src.controllers.auth import current, editor
from src.schemas.requests import CompareInput
from src.services.comparison import compare, get_comparison, list_comparisons
from src.utils.serialize import row

router = APIRouter()


@router.get('/comparisons')
def comparisons(db=Depends(database), u=Depends(current)):
    return [row(x) for x in list_comparisons(db)]


@router.post('/comparisons')
def create(b: CompareInput, db=Depends(database), u=Depends(editor)):
    return row(compare(db, u, b.base_run_id, b.head_run_id))


@router.get('/comparisons/{id}')
def detail(id: int, db=Depends(database), u=Depends(current)):
    return row(get_comparison(db, id))
