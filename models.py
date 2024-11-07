from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True)
    description = Column(String, index=True)
    images = relationship("ImageData", back_populates="task")

class ImageData(Base):
    __tablename__ = "images"
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"))
    image_path = Column(String, index=True)
    task = relationship("Task", back_populates="images")
