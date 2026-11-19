from sqlalchemy import Column,Integer,String,JSON,Text,Float,Boolean,UniqueConstraint
from src.config.database import Base
class Run(Base):
 __tablename__='oeeruns'
 id=Column(Integer,primary_key=True); name=Column(String(120)); status=Column(String(20)); snapshot=Column(JSON); checksum=Column(String(64)); result=Column(JSON); error=Column(Text); created=Column(Float); approved=Column(Boolean,default=False); review=Column(Text,default='')
class Schedule(Base):
 __tablename__='delivery_schedules'
 id=Column(Integer,primary_key=True); name=Column(String(120)); run_id=Column(Integer); interval_seconds=Column(Integer); next_at=Column(Float); enabled=Column(Boolean,default=True)
class Delivery(Base):
 __tablename__='deliveries'
 id=Column(Integer,primary_key=True); schedule_id=Column(Integer); run_id=Column(Integer); due_key=Column(String(120),unique=True); created=Column(Float); payload=Column(JSON)
class RunComparison(Base):
 """两份已复核报告冻结底稿的差值归因；同一对报告唯一，重跑复用既有结论。"""
 __tablename__='run_comparisons'
 id=Column(Integer,primary_key=True); base_run_id=Column(Integer,nullable=False); head_run_id=Column(Integer,nullable=False); pair_key=Column(String(64),nullable=False,unique=True); status=Column(String(20),nullable=False); checksum=Column(String(64)); result=Column(JSON); error=Column(Text); actor=Column(String(120)); created=Column(Float)
 __table_args__=(UniqueConstraint('base_run_id','head_run_id',name='uq_comparison_pair'),)
