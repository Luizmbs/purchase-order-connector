import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, server_default="operator")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    refresh_tokens: Mapped[list["RefreshTokenModel"]] = relationship(back_populates="user")


class RefreshTokenModel(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user: Mapped["UserModel"] = relationship(back_populates="refresh_tokens")

    __table_args__ = (
        Index("ix_refresh_tokens_token_hash", "token_hash"),
        Index("ix_refresh_tokens_user_id", "user_id"),
    )


class ClientModel(Base):
    __tablename__ = "clients"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    format_type: Mapped[str] = mapped_column(String(50), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    purchase_orders: Mapped[list["PurchaseOrderModel"]] = relationship(back_populates="client")


class PurchaseOrderModel(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[str] = mapped_column(String(50), ForeignKey("clients.id"), nullable=False)
    po_number: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="BRL")
    vendor_tax_id: Mapped[str] = mapped_column(String(14), nullable=False)
    vendor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    client: Mapped["ClientModel"] = relationship(back_populates="purchase_orders")
    items: Mapped[list["PurchaseOrderItemModel"]] = relationship(back_populates="purchase_order", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("client_id", "po_number", name="uq_purchase_orders_client_po"),
        Index("ix_purchase_orders_client_id", "client_id"),
        Index("ix_purchase_orders_vendor_tax_id", "vendor_tax_id"),
        Index("ix_purchase_orders_status", "status"),
        Index("ix_purchase_orders_loaded_at", "loaded_at"),
    )


class PurchaseOrderItemModel(Base):
    __tablename__ = "purchase_order_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("purchase_orders.id"), nullable=False)
    line: Mapped[int] = mapped_column(Integer, nullable=False)
    material: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    uom: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity_ordered: Mapped[Decimal] = mapped_column(Numeric(15, 3), nullable=False)
    quantity_received: Mapped[Decimal] = mapped_column(Numeric(15, 3), nullable=False, server_default="0")
    unit_price: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    item_created_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    purchase_order: Mapped["PurchaseOrderModel"] = relationship(back_populates="items")

    __table_args__ = (
        UniqueConstraint("purchase_order_id", "line", name="uq_purchase_order_items_po_line"),
        Index("ix_purchase_order_items_po_id", "purchase_order_id"),
        Index("ix_purchase_order_items_po_material", "purchase_order_id", "material"),
    )


class ConferenceModel(Base):
    __tablename__ = "conferences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("purchase_orders.id"), nullable=True)
    client_id: Mapped[str] = mapped_column(String(50), ForeignKey("clients.id"), nullable=False)
    po_number: Mapped[str] = mapped_column(String(100), nullable=False)
    invoice_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    vendor_tax_id: Mapped[str] = mapped_column(String(14), nullable=False)
    result: Mapped[str] = mapped_column(String(10), nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    divergences: Mapped[list["ConferenceDivergenceModel"]] = relationship(back_populates="conference", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_conferences_result", "result"),
        Index("ix_conferences_checked_at", "checked_at"),
        Index("ix_conferences_client_id", "client_id"),
    )


class ConferenceDivergenceModel(Base):
    __tablename__ = "conference_divergences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conference_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conferences.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    item_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    material: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expected: Mapped[str | None] = mapped_column(String(255), nullable=True)
    received: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detail: Mapped[str] = mapped_column(String(500), nullable=False)

    conference: Mapped["ConferenceModel"] = relationship(back_populates="divergences")

    __table_args__ = (
        Index("ix_conference_divergences_conference_id", "conference_id"),
    )
