import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text
from app.database import Base

class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    status = Column(String, default="PENDING", nullable=False) # PENDING, PROCESSING, SUCCESS, FAILED
    progress = Column(Integer, default=0, nullable=False)       # 0 to 100 percent
    error_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)
    
    # Store the final assessment-compliant JSON schema as serialized text
    metadata_json = Column(Text, nullable=True)

    def to_dict(self):
        """Converts the task row database record into a clean dictionary."""
        return {
            "id": self.id,
            "filename": self.filename,
            "status": self.status,
            "progress": self.progress,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
