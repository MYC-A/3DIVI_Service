from sqlalchemy import Column, Integer, String, ForeignKey, JSON, BigInteger, DateTime
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True)
    description = Column(String, index=True)
    images = relationship("ImageData", back_populates="task")
    status = Column(String, index=True, default='not_requested')
    timestamp_of_request = Column(DateTime, index=True, default=datetime.utcnow)


class ImageData(Base):
    __tablename__ = "images"
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"))
    image_path = Column(String, index=True)
    additional_data = Column(JSON)           # поле JSON для хранения произвольных данных

    task = relationship("Task", back_populates="images")
