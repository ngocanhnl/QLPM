from datetime import date, time, timedelta

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.schedule import Schedule
from app.models.weekly_shift import WeeklyShift


class ScheduleService:
    @staticmethod
    def list_doctor_schedules(*, doctor_id: int) -> list[Schedule]:
        stmt = db.select(Schedule).where(Schedule.doctor_id == doctor_id).order_by(
            Schedule.date.desc(), Schedule.start_time.desc()
        )
        return list(db.session.execute(stmt).scalars().all())

    @staticmethod
    def create_schedule(
        *, doctor_id: int, date_value: date, start_time_value: time, end_time_value: time, is_available: bool
    ) -> Schedule:
        schedule = Schedule(
            doctor_id=doctor_id,
            date=date_value,
            start_time=start_time_value,
            end_time=end_time_value,
            is_available=is_available,
        )
        db.session.add(schedule)
        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            raise ValueError("This time slot already exists") from e
        return schedule

    @staticmethod
    def ensure_next_days_from_weekly_shifts(*, doctor_id: int, days_ahead: int = 7) -> int:
        if days_ahead < 1:
            return 0

        shifts = list(
            db.session.execute(
                db.select(WeeklyShift)
                .where(WeeklyShift.doctor_id == doctor_id, WeeklyShift.is_active.is_(True))
                .order_by(WeeklyShift.weekday, WeeklyShift.start_time)
            ).scalars().all()
        )
        if not shifts:
            return 0

        created = 0
        start_date = date.today()
        end_date = start_date + timedelta(days=days_ahead - 1)

        existing_rows = db.session.execute(
            db.select(Schedule.date, Schedule.start_time, Schedule.end_time).where(
                Schedule.doctor_id == doctor_id,
                Schedule.date >= start_date,
                Schedule.date <= end_date,
            )
        ).all()
        existing = {(r[0], r[1], r[2]) for r in existing_rows}

        for i in range(days_ahead):
            d = start_date + timedelta(days=i)
            weekday = d.weekday()
            for sh in shifts:
                if sh.weekday != weekday:
                    continue
                key = (d, sh.start_time, sh.end_time)
                if key in existing:
                    continue
                db.session.add(
                    Schedule(
                        doctor_id=doctor_id,
                        date=d,
                        start_time=sh.start_time,
                        end_time=sh.end_time,
                        is_available=True,
                    )
                )
                created += 1
                existing.add(key)

        if created:
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
        return created

    @staticmethod
    def update_schedule(
        *,
        schedule: Schedule,
        date_value: date,
        start_time_value: time,
        end_time_value: time,
        is_available: bool,
    ) -> Schedule:
        schedule.date = date_value
        schedule.start_time = start_time_value
        schedule.end_time = end_time_value
        schedule.is_available = is_available
        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            raise ValueError("This time slot already exists") from e
        return schedule

    @staticmethod
    def delete_schedule(schedule: Schedule) -> None:
        if schedule.appointment:
            raise ValueError("Cannot delete: this slot already has an appointment")
        db.session.delete(schedule)
        db.session.commit()

