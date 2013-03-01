""" Realization of TaskWarrior tasks. """
import taskw
import twgs

from datetime import datetime
from twiggy import log

class TaskWarriorTask(twgs.Task, twgs.DownstreamTask):
    """ Represents a TaskWarrior task. """
    __UDA_NAMESPACE = "twgs"
    __UDA_ASSOCIATION = "%s_assoc" % __UDA_NAMESPACE
    __UDA_ETAG = "%s_etag" % __UDA_NAMESPACE

    def __init__(self, source):
        super(TaskWarriorTask, self).__init__()
        self._source = source

    def stale(self, other):
        """ Identifies if this task is stale from upstream. """
        if not TaskWarriorTask.__UDA_ETAG in self._source:
            # Is local only. Couldn't possibly be upstream.
            return False
        return self._source[TaskWarriorTask.__UDA_ETAG] != other.etag

    def copy_from(self, other):
        if other is None:
            raise ValueError("Cannot sync with nothing.")
        dfmt = self.__format_date # Format callback.
        self._set_or_delete('project', other.project)
        self._set_or_delete('description', other.subject)
        self._set_or_delete('due', other.due, fmt=dfmt)
        self._set_or_delete('end', other.completed, fmt=dfmt)

    @property
    def should_sync(self):
        if self.status == 'recurring' or self.is_deleted:
            # Don't send these upstream. They don't exist.
            return False

        elif self.is_completed and self.association is None:
            # The task was completed locally. Probably not much value.
            return False

        else:
            return True

    @property
    def uid(self):
        return self._source.get('uuid', None)

    @property
    def status(self):
        return self._source['status']

    @property
    def project(self):
        return self._source.get('project', None)

    @property
    def subject(self):
        return self._source['description']

    @property
    def due(self):
        return self.__parse_date(self._source.get('due', None))

    @property
    def completed(self):
        return self.__parse_date(self._source.get('end', None))

    @property
    def annotations(self):
        """ Gets a dict of annotations. """
        annotations = {}
        for key in self._source.keys():
            if key.startswith('annotation_'):
                annotations[key] = self._source[key]
        return annotations

    @property
    def association(self):
        """ Gets the upstream identifier for this task. """
        for key in self._source.keys():
            if key.startswith(TaskWarriorTask.__UDA_ASSOCIATION):
                return self._source[key]
        return None

    def is_associated_with(self, other):
        """ Identifies if this task is associated with the specified task. """
        association_key = self._association_key_for(other)
        if association_key in self._source:
            return self._source[association_key] == other.uid
        return False

    def associate_with(self, other):
        """ Associate the specified associable with this instance.  """
        association_key = self._association_key_for(other)
        self._source[association_key] = other.uid
        self._source[TaskWarriorTask.__UDA_ETAG] = other.etag

    def _association_key_for(self, upstream):
        """ Generate the association key for the upstream. """
        return "%s_%s" % (TaskWarriorTask.__UDA_ASSOCIATION, upstream.provider)

    def __parse_date(self, as_string):
        if as_string is None:
            return None
        return datetime.fromtimestamp(int(as_string))

    def __format_date(self, as_timestamp):
        return datetime.strftime(as_timestamp, '%s')

class TaskWarriorTaskFactory(twgs.TaskFactory):
    def create_from(self, **kwargs):
        """ Create a new task from another task, 'other', or a map, 'map'. """
        if 'map' in kwargs:
            return TaskWarriorTask(kwargs['map'].copy())

        elif 'other' in kwargs:
            task = TaskWarriorTask({'status':'pending'})
            task.copy_from(kwargs['other'])
            return task

        raise KeyError('Either a map or task argument must be provided.')

class TaskWarriorTaskRepository(twgs.TaskRepository):
    def __init__(self, factory, db=None, **kwargs):
        self._db = db or taskw.TaskWarrior(config_filename=kwargs['config'])
        self._factory = factory

    def all(self):
        wtasks = self._db.load_tasks()
        wtasks = sum(wtasks.values(), [])
        return [self._factory.create_from(map=t) for t in wtasks]

    def delete(self, task):
        self._db.task_delete(uuid=task.uid)

    def save(self, task):
        if task.uid is None:
            task._source = self._db.task_add(**task._source)
        else:
            self._db.task_update(task._source)

        if task.is_pending and not task.completed is None:
            log.info("Marking {0} as complete.", task)
            keys = {k:task._source[k]
                    for k in task._source.keys()
                    if k == 'uuid' or k == 'end'}
            task._source = self._db.task_done(**keys)
