"""Import every model module so the metadata registry is complete.

ORM mappers resolve foreign keys against ``Base.metadata``; a module that
declares a cross-module foreign key fails to configure unless the target model
was imported as well. Importing this package (or ``app.models``) guarantees a
complete registry for the API runtime, Alembic and tests.
"""

from app.anamnesis import models as anamnesis_models  # noqa: F401
from app.auth import models as auth_models  # noqa: F401
from app.clinics import models as clinics_models  # noqa: F401
from app.documents import models as documents_models  # noqa: F401
from app.patients import models as patients_models  # noqa: F401
from app.users import models as users_models  # noqa: F401
