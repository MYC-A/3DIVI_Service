from termios import CIBAUD

from sqlalchemy import Column, Integer, String, ForeignKey,JSON
from sqlalchemy.orm import relationship, Relationship
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
    additional_data = Column(JSON)           # поле JSON для хранения произвольных данных

    task = relationship("Task", back_populates="images")

class DetectionData(Base):
    __tablename__ = "detection"
    id = Column(Integer, primary_key=True, index=True)
    image_id = Column(Integer, ForeignKey("images.id"))
    detection = Column(JSON)
    template = Column(JSON)


