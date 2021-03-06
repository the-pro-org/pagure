# -*- coding: utf-8 -*-

"""
 (c) 2014-2018 - Copyright Red Hat Inc

 Authors:
   Pierre-Yves Chibon <pingou@pingoured.fr>
   Farhaan Bukhsh <farhaan.bukhsh@gmail.com>

"""

import datetime
import logging
from math import ceil

import flask
from sqlalchemy.exc import SQLAlchemyError

import pagure.exceptions
import pagure.lib
import pagure.lib.git
import pagure.forms
import pagure.ui.filters
from pagure.config import config as pagure_config
from pagure.flask_app import _get_user, admin_session_timedout
from pagure.ui import UI_NS
from pagure.utils import (
    authenticated,
    is_safe_url,
    login_required,
    get_task_redirect_url,
)


_log = logging.getLogger(__name__)


def _filter_acls(repos, acl, user):
    """ Filter the given list of repositories to return only the ones where
    the user has the specified acl.
    """
    if acl == 'commit':
        repos = [
            repo
            for repo in repos
            if user in repo.committers
            or user.username == repo.user.username
        ]
    elif acl == 'admin':
        repos = [
            repo
            for repo in repos
            if user in repo.admins
            or user.username == repo.user.username
        ]
    elif acl == 'main admin':
        repos = [
            repo
            for repo in repos
            if user.username == repo.user.username
        ]

    return repos


@UI_NS.route('/browse/projects', endpoint='browse_projects')
@UI_NS.route('/browse/projects/', endpoint='browse_projects')
@UI_NS.route('/')
def index():
    """ Front page of the application.
    """
    sorting = flask.request.args.get('sorting') or None
    page = flask.request.args.get('page', 1)
    try:
        page = int(page)
        if page < 1:
            page = 1
    except ValueError:
        page = 1

    limit = pagure_config['ITEM_PER_PAGE']
    start = limit * (page - 1)

    repos = pagure.lib.search_projects(
        flask.g.session,
        fork=False,
        start=start,
        limit=limit,
        sort=sorting)

    num_repos = pagure.lib.search_projects(
        flask.g.session,
        fork=False,
        count=True)
    total_page = int(ceil(num_repos / float(limit)) if num_repos > 0 else 1)

    if authenticated() and flask.request.path == '/':
        return index_auth()

    return flask.render_template(
        'index.html',
        select="projects",
        repos=repos,
        repos_length=num_repos,
        total_page=total_page,
        page=page,
        sorting=sorting,
    )


def index_auth():
    """ Front page for authenticated user.
    """
    user = _get_user(username=flask.g.fas_user.username)

    acl = flask.request.args.get('acl', '').strip().lower() or None

    repopage = flask.request.args.get('repopage', 1)
    try:
        repopage = int(repopage)
        if repopage < 1:
            repopage = 1
    except ValueError:
        repopage = 1

    forkpage = flask.request.args.get('forkpage', 1)
    try:
        forkpage = int(forkpage)
        if forkpage < 1:
            forkpage = 1
    except ValueError:
        forkpage = 1

    repos = pagure.lib.search_projects(
        flask.g.session,
        username=flask.g.fas_user.username,
        exclude_groups=pagure_config.get('EXCLUDE_GROUP_INDEX'),
        fork=False, private=flask.g.fas_user.username)
    if repos and acl:
        repos = _filter_acls(repos, acl, user)

    repos_length = len(repos)

    forks = pagure.lib.search_projects(
        flask.g.session,
        username=flask.g.fas_user.username,
        fork=True,
        private=flask.g.fas_user.username)

    forks_length = len(forks)

    watch_list = pagure.lib.user_watch_list(
        flask.g.session,
        user=flask.g.fas_user.username,
        exclude_groups=pagure_config.get('EXCLUDE_GROUP_INDEX'),
    )

    return flask.render_template(
        'index_auth.html',
        username=flask.g.fas_user.username,
        user=user,
        forks=forks,
        repos=repos,
        watch_list=watch_list,
        repopage=repopage,
        forkpage=forkpage,
        repos_length=repos_length,
        forks_length=forks_length,
    )


@UI_NS.route('/search/')
@UI_NS.route('/search')
def search():
    """ Search this pagure instance for projects or users.
    """
    stype = flask.request.args.get('type', 'projects')
    term = flask.request.args.get('term')
    page = flask.request.args.get('page', 1)
    direct = flask.request.values.get('direct', None)
    if str(direct).lower() in ['1', 'true']:
        direct = True
    else:
        direct = False

    try:
        page = int(page)
        if page < 1:
            page = 1
    except ValueError:
        page = 1

    if direct:
        return flask.redirect(
            flask.url_for('ui_ns.view_repo', repo='') + term
        )

    if stype == 'projects':
        return flask.redirect(flask.url_for(
            'ui_ns.view_projects', pattern=term))
    elif stype == 'projects_forks':
        return flask.redirect(flask.url_for(
            'view_projects', pattern=term, forks=True))
    elif stype == 'groups':
        return flask.redirect(flask.url_for(
            'ui_ns.view_group', group=term))
    else:
        return flask.redirect(flask.url_for(
            'ui_ns.view_users', username=term))


@UI_NS.route('/users/')
@UI_NS.route('/users')
@UI_NS.route('/users/<username>')
def view_users(username=None):
    """ Present the list of users.
    """
    page = flask.request.args.get('page', 1)
    try:
        page = int(page)
        if page < 1:
            page = 1
    except ValueError:
        page = 1

    users = pagure.lib.search_user(flask.g.session, pattern=username)

    private = False
    # Condition to check non-authorized user should't be able to access private
    # project of other users
    if authenticated() and username == flask.g.fas_user.username:
        private = flask.g.fas_user.username

    if len(users) == 1:
        flask.flash('Only one result found, redirecting you to it')
        return flask.redirect(
            flask.url_for('ui_ns.view_user', username=users[0].username))

    limit = pagure_config['ITEM_PER_PAGE']
    start = limit * (page - 1)
    end = limit * page
    users_length = len(users)
    users = users[start:end]

    total_page = int(ceil(users_length / float(limit)))

    for user in users:
        repos_length = pagure.lib.search_projects(
            flask.g.session,
            username=user.user,
            fork=False,
            count=True,
            private=private)

        forks_length = pagure.lib.search_projects(
            flask.g.session,
            username=user.user,
            fork=True,
            count=True,
            private=private)
        user.repos_length = repos_length
        user.forks_length = forks_length

    return flask.render_template(
        'user_list.html',
        users=users,
        users_length=users_length,
        total_page=total_page,
        page=page,
        select='users',
    )


@UI_NS.route('/projects/')
@UI_NS.route('/projects')
@UI_NS.route('/projects/<pattern>')
@UI_NS.route('/projects/<namespace>/<pattern>')
def view_projects(pattern=None, namespace=None):
    """ Present the list of projects.
    """
    forks = flask.request.args.get('forks')
    page = flask.request.args.get('page', 1)

    try:
        page = int(page)
        if page < 1:
            page = 1
    except ValueError:
        page = 1

    select = 'projects'
    # If forks is specified, we want both forks and projects
    if str(forks).lower() in ['true', '1']:
        forks = None
        select = 'projects_forks'
    else:
        forks = False
    private = False

    if authenticated():
        private = flask.g.fas_user.username

    limit = pagure_config['ITEM_PER_PAGE']
    start = limit * (page - 1)

    projects = pagure.lib.search_projects(
        flask.g.session, pattern=pattern, namespace=namespace,
        fork=forks, start=start, limit=limit, private=private)

    if len(projects) == 1:
        flask.flash('Only one result found, redirecting you to it')
        return flask.redirect(flask.url_for(
            'ui_ns.view_repo', repo=projects[0].name,
            namespace=projects[0].namespace,
            username=projects[0].user.username if projects[0].is_fork else None
        ))

    projects_length = pagure.lib.search_projects(
        flask.g.session, pattern=pattern, namespace=namespace,
        fork=forks, count=True, private=private)

    total_page = int(ceil(projects_length / float(limit)))

    return flask.render_template(
        'index.html',
        repos=projects,
        repos_length=projects_length,
        total_page=total_page,
        page=page,
        select=select,
    )


@UI_NS.route('/user/<username>/')
@UI_NS.route('/user/<username>')
def view_user(username):
    """ Front page of a specific user.
    """
    user = _get_user(username=username)

    acl = flask.request.args.get('acl', '').strip().lower() or None

    repopage = flask.request.args.get('repopage', 1)
    try:
        repopage = int(repopage)
        if repopage < 1:
            repopage = 1
    except ValueError:
        repopage = 1

    forkpage = flask.request.args.get('forkpage', 1)
    try:
        forkpage = int(forkpage)
        if forkpage < 1:
            forkpage = 1
    except ValueError:
        forkpage = 1

    limit = pagure_config['ITEM_PER_PAGE']
    repo_start = limit * (repopage - 1)
    fork_start = limit * (forkpage - 1)

    private = False
    if authenticated() and username == flask.g.fas_user.username:
        private = flask.g.fas_user.username

    repos = pagure.lib.search_projects(
        flask.g.session,
        username=username,
        fork=False,
        exclude_groups=pagure_config.get('EXCLUDE_GROUP_INDEX'),
        start=repo_start,
        limit=limit,
        private=private)

    if repos and acl:
        repos = _filter_acls(repos, acl, user)

    repos_length = pagure.lib.search_projects(
        flask.g.session,
        username=username,
        fork=False,
        exclude_groups=pagure_config.get('EXCLUDE_GROUP_INDEX'),
        private=private,
        count=True)

    forks = pagure.lib.search_projects(
        flask.g.session,
        username=username,
        fork=True,
        start=fork_start,
        limit=limit,
        private=private)

    forks_length = pagure.lib.search_projects(
        flask.g.session,
        username=username,
        fork=True,
        private=private,
        count=True)

    total_page_repos = int(ceil(repos_length / float(limit)))
    total_page_forks = int(ceil(forks_length / float(limit)))

    return flask.render_template(
        'user_info.html',
        username=username,
        user=user,
        repos=repos,
        total_page_repos=total_page_repos,
        forks=forks,
        total_page_forks=total_page_forks,
        repopage=repopage,
        forkpage=forkpage,
        repos_length=repos_length,
        forks_length=forks_length,
    )


@UI_NS.route('/user/<username>/requests/')
@UI_NS.route('/user/<username>/requests')
def view_user_requests(username):
    """ Shows the pull-requests for the specified user.
    """
    user = _get_user(username=username)

    requests = pagure.lib.get_pull_request_of_user(
        flask.g.session,
        username=username
    )

    return flask.render_template(
        'user_requests.html',
        username=username,
        user=user,
        requests=requests,
    )


@UI_NS.route('/user/<username>/issues/')
@UI_NS.route('/user/<username>/issues')
def view_user_issues(username):
    """
    Shows the issues created or assigned to the specified user.

    :param username: The username to retrieve the issues for
    :type  username: str
    """

    if not pagure_config.get('ENABLE_TICKETS', True):
        flask.abort(404, 'Tickets have been disabled on this pagure instance')

    user = _get_user(username=username)

    return flask.render_template(
        'user_issues.html',
        username=username,
        user=user,
    )


@UI_NS.route('/user/<username>/stars/')
@UI_NS.route('/user/<username>/stars')
def view_user_stars(username):
    """
    Shows the starred projects of the specified user.

    :arg username: The username whose stars we have to retrieve
    """

    user = _get_user(username=username)

    return flask.render_template(
        'user_stars.html',
        username=username,
        user=user,
        repos=[star.project for star in user.stars],
    )


@UI_NS.route('/new/', methods=('GET', 'POST'))
@UI_NS.route('/new', methods=('GET', 'POST'))
@login_required
def new_project():
    """ Form to create a new project.
    """
    user = pagure.lib.search_user(
        flask.g.session, username=flask.g.fas_user.username)

    if not pagure_config.get('ENABLE_NEW_PROJECTS', True) or \
            not pagure_config.get('ENABLE_UI_NEW_PROJECTS', True):
        flask.abort(404, 'Creation of new project is not allowed on this \
                pagure instance')

    namespaces = pagure_config['ALLOWED_PREFIX'][:]
    if user:
        namespaces.extend([grp for grp in user.groups])
    if pagure_config.get('USER_NAMESPACE', False):
        namespaces.insert(0, flask.g.fas_user.username)

    form = pagure.forms.ProjectForm(namespaces=namespaces)

    if form.validate_on_submit():
        name = form.name.data
        description = form.description.data
        url = form.url.data
        avatar_email = form.avatar_email.data
        create_readme = form.create_readme.data
        private = False
        if pagure_config.get('PRIVATE_PROJECTS', False):
            private = form.private.data
        namespace = form.namespace.data
        if namespace:
            namespace = namespace.strip()

        try:
            task = pagure.lib.new_project(
                flask.g.session,
                name=name,
                private=private,
                description=description,
                namespace=namespace,
                url=url,
                avatar_email=avatar_email,
                user=flask.g.fas_user.username,
                blacklist=pagure_config['BLACKLISTED_PROJECTS'],
                allowed_prefix=pagure_config['ALLOWED_PREFIX'],
                gitfolder=pagure_config['GIT_FOLDER'],
                docfolder=pagure_config.get('DOCS_FOLDER'),
                ticketfolder=pagure_config.get('TICKETS_FOLDER'),
                requestfolder=pagure_config['REQUESTS_FOLDER'],
                add_readme=create_readme,
                userobj=user,
                prevent_40_chars=pagure_config.get(
                    'OLD_VIEW_COMMIT_ENABLED', False),
                user_ns=pagure_config.get('USER_NAMESPACE', False),
            )
            flask.g.session.commit()
            return pagure.utils.wait_for_task(task)
        except pagure.exceptions.PagureException as err:
            flask.flash(str(err), 'error')
        except SQLAlchemyError as err:  # pragma: no cover
            flask.g.session.rollback()
            flask.flash(str(err), 'error')

    return flask.render_template(
        'new_project.html',
        form=form,
    )


@UI_NS.route('/wait/<taskid>')
def wait_task(taskid):
    """ Shows a wait page until the task finishes. """
    task = pagure.lib.tasks.get_result(taskid)

    is_js = flask.request.args.get('js')
    if str(is_js).lower() == '1':
        is_js = True
    else:
        is_js = False

    prev = flask.request.args.get('prev')
    if not is_safe_url(prev):
        prev = flask.url_for('index')

    count = flask.request.args.get('count', 0)
    try:
        count = int(count)
        if count < 1:
            count = 0
    except ValueError:
        count = 0

    if task.ready():
        if is_js:
            flask.abort(417)
        return flask.redirect(get_task_redirect_url(task, prev))
    else:
        if is_js:
            return flask.jsonify({
                'count': count + 1,
                'status': task.status,
            })

        return flask.render_template(
            'waiting.html',
            task=task,
            count=count,
            prev=prev,
        )


@UI_NS.route('/settings/', methods=('GET', 'POST'))
@UI_NS.route('/settings', methods=('GET', 'POST'))
@login_required
def user_settings():
    """ Update the user settings.
    """
    if admin_session_timedout():
        return flask.redirect(
            flask.url_for('auth_login', next=flask.request.url))

    user = _get_user(username=flask.g.fas_user.username)

    form = pagure.forms.UserSettingsForm()
    if form.validate_on_submit() and pagure_config.get('LOCAL_SSH_KEY', True):
        ssh_key = form.ssh_key.data

        try:
            message = 'Nothing to update'
            if user.public_ssh_key != ssh_key:
                pagure.lib.update_user_ssh(
                    flask.g.session,
                    user=user,
                    ssh_key=ssh_key,
                    keydir=pagure_config.get('GITOLITE_KEYDIR', None),
                )
                flask.g.session.commit()
                message = 'Public ssh key updated'
            flask.flash(message)
            return flask.redirect(
                flask.url_for('ui_ns.user_settings'))
        except SQLAlchemyError as err:  # pragma: no cover
            flask.g.session.rollback()
            flask.flash(str(err), 'error')
    elif flask.request.method == 'GET':
        form.ssh_key.data = user.public_ssh_key

    return flask.render_template(
        'user_settings.html',
        user=user,
        form=form,
    )


@UI_NS.route('/settings/usersettings', methods=['POST'])
@login_required
def update_user_settings():
    """ Update the user's settings set in the settings page.
    """
    if admin_session_timedout():
        if flask.request.method == 'POST':
            flask.flash('Action canceled, try it again', 'error')
        return flask.redirect(
            flask.url_for('auth_login', next=flask.request.url))

    user = _get_user(username=flask.g.fas_user.username)

    form = pagure.forms.ConfirmationForm()

    if form.validate_on_submit():
        settings = {}
        for key in flask.request.form:
            if key == 'csrf_token':
                continue
            settings[key] = flask.request.form[key]

        try:
            message = pagure.lib.update_user_settings(
                flask.g.session,
                settings=settings,
                user=user.username,
            )
            flask.g.session.commit()
            flask.flash(message)
        except pagure.exceptions.PagureException as msg:
            flask.g.session.rollback()
            flask.flash(msg, 'error')
        except SQLAlchemyError as err:  # pragma: no cover
            flask.g.session.rollback()
            flask.flash(str(err), 'error')

    return flask.redirect(flask.url_for('ui_ns.user_settings'))


@UI_NS.route('/markdown/', methods=['POST'])
def markdown_preview():
    """ Return the provided markdown text in html.

    The text has to be provided via the parameter 'content' of a POST query.
    """
    form = pagure.forms.ConfirmationForm()
    if form.validate_on_submit():
        return pagure.ui.filters.markdown_filter(flask.request.form['content'])
    else:
        flask.abort(400, 'Invalid request')


@UI_NS.route('/settings/email/drop', methods=['POST'])
@login_required
def remove_user_email():
    """ Remove the specified email from the logged in user.
    """
    if admin_session_timedout():
        return flask.redirect(
            flask.url_for('auth_login', next=flask.request.url))

    user = _get_user(username=flask.g.fas_user.username)

    if len(user.emails) == 1:
        flask.flash(
            'You must always have at least one email', 'error')
        return flask.redirect(
            flask.url_for('ui_ns.user_settings')
        )

    form = pagure.forms.UserEmailForm()

    if form.validate_on_submit():
        email = form.email.data
        useremails = [mail.email for mail in user.emails]

        if email not in useremails:
            flask.flash(
                'You do not have the email: %s, nothing to remove' % email,
                'error')
            return flask.redirect(
                flask.url_for('ui_ns.user_settings')
            )

        for mail in user.emails:
            if mail.email == email:
                user.emails.remove(mail)
                break
        try:
            flask.g.session.commit()
            flask.flash('Email removed')
        except SQLAlchemyError as err:  # pragma: no cover
            flask.g.session.rollback()
            _log.exception(err)
            flask.flash('Email could not be removed', 'error')

    return flask.redirect(flask.url_for('ui_ns.user_settings'))


@UI_NS.route('/settings/email/add/', methods=['GET', 'POST'])
@UI_NS.route('/settings/email/add', methods=['GET', 'POST'])
@login_required
def add_user_email():
    """ Add a new email for the logged in user.
    """
    if admin_session_timedout():
        return flask.redirect(
            flask.url_for('auth_login', next=flask.request.url))

    user = _get_user(username=flask.g.fas_user.username)

    form = pagure.forms.UserEmailForm(
        emails=[mail.email for mail in user.emails])
    if form.validate_on_submit():
        email = form.email.data

        try:
            pagure.lib.add_user_pending_email(flask.g.session, user, email)
            flask.g.session.commit()
            flask.flash('Email pending validation')
            return flask.redirect(flask.url_for('ui_ns.user_settings'))
        except pagure.exceptions.PagureException as err:
            flask.flash(str(err), 'error')
        except SQLAlchemyError as err:  # pragma: no cover
            flask.g.session.rollback()
            _log.exception(err)
            flask.flash('Email could not be added', 'error')

    return flask.render_template(
        'user_emails.html',
        user=user,
        form=form,
    )


@UI_NS.route('/settings/email/default', methods=['POST'])
@login_required
def set_default_email():
    """ Set the default email address of the user.
    """
    if admin_session_timedout():
        return flask.redirect(
            flask.url_for('auth_login', next=flask.request.url))

    user = _get_user(username=flask.g.fas_user.username)

    form = pagure.forms.UserEmailForm()
    if form.validate_on_submit():
        email = form.email.data
        useremails = [mail.email for mail in user.emails]

        if email not in useremails:
            flask.flash(
                'You do not have the email: %s, nothing to set' % email,
                'error')

            return flask.redirect(
                flask.url_for('ui_ns.user_settings')
            )

        user.default_email = email

        try:
            flask.g.session.commit()
            flask.flash('Default email set to: %s' % email)
        except SQLAlchemyError as err:  # pragma: no cover
            flask.g.session.rollback()
            _log.exception(err)
            flask.flash('Default email could not be set', 'error')

    return flask.redirect(flask.url_for('ui_ns.user_settings'))


@UI_NS.route('/settings/email/resend', methods=['POST'])
@login_required
def reconfirm_email():
    """ Re-send the email address of the user.
    """
    if admin_session_timedout():
        return flask.redirect(
            flask.url_for('auth_login', next=flask.request.url))

    user = _get_user(username=flask.g.fas_user.username)

    form = pagure.forms.UserEmailForm()
    if form.validate_on_submit():
        email = form.email.data

        try:
            pagure.lib.resend_pending_email(flask.g.session, user, email)
            flask.g.session.commit()
            flask.flash('Confirmation email re-sent')
        except pagure.exceptions.PagureException as err:
            flask.flash(str(err), 'error')
        except SQLAlchemyError as err:  # pragma: no cover
            flask.g.session.rollback()
            _log.exception(err)
            flask.flash('Confirmation email could not be re-sent', 'error')

    return flask.redirect(flask.url_for('ui_ns.user_settings'))


@UI_NS.route('/settings/email/confirm/<token>/')
@UI_NS.route('/settings/email/confirm/<token>')
def confirm_email(token):
    """ Confirm a new email.
    """
    if admin_session_timedout():
        return flask.redirect(
            flask.url_for('auth_login', next=flask.request.url))

    email = pagure.lib.search_pending_email(flask.g.session, token=token)
    if not email:
        flask.flash('No email associated with this token.', 'error')
    else:
        try:
            pagure.lib.add_email_to_user(
                flask.g.session, email.user, email.email)
            flask.g.session.delete(email)
            flask.g.session.commit()
            flask.flash('Email validated')
        except SQLAlchemyError as err:  # pragma: no cover
            flask.g.session.rollback()
            flask.flash(
                'Could not set the account as active in the db, '
                'please report this error to an admin', 'error')
            _log.exception(err)

    return flask.redirect(flask.url_for('ui_ns.user_settings'))


@UI_NS.route('/ssh_info/')
@UI_NS.route('/ssh_info')
def ssh_hostkey():
    """ Endpoint returning information about the SSH hostkey and fingerprint
    of the current pagure instance.
    """
    return flask.render_template(
        'doc_ssh_keys.html',
    )


@UI_NS.route('/settings/token/new/', methods=('GET', 'POST'))
@UI_NS.route('/settings/token/new', methods=('GET', 'POST'))
@login_required
def add_api_user_token():
    """ Create an user token (not project specific).
    """
    if admin_session_timedout():
        if flask.request.method == 'POST':
            flask.flash('Action canceled, try it again', 'error')
        return flask.redirect(
            flask.url_for('auth_login', next=flask.request.url))

    # Ensure the user is in the DB at least
    user = _get_user(username=flask.g.fas_user.username)

    acls = pagure.lib.get_acls(
        flask.g.session, restrict=pagure_config.get('CROSS_PROJECT_ACLS'))
    form = pagure.forms.NewTokenForm(acls=acls)

    if form.validate_on_submit():
        try:
            msg = pagure.lib.add_token_to_user(
                flask.g.session,
                project=None,
                description=form.description.data.strip() or None,
                acls=form.acls.data,
                username=user.username,
            )
            flask.g.session.commit()
            flask.flash(msg)
            return flask.redirect(flask.url_for('ui_ns.user_settings'))
        except SQLAlchemyError as err:  # pragma: no cover
            flask.g.session.rollback()
            _log.exception(err)
            flask.flash('API key could not be added', 'error')

    # When form is displayed after an empty submission, show an error.
    if form.errors.get('acls'):
        flask.flash('You must select at least one permission.', 'error')

    return flask.render_template(
        'add_token.html',
        select='settings',
        form=form,
        acls=acls,
    )


@UI_NS.route('/settings/token/revoke/<token_id>/', methods=['POST'])
@UI_NS.route('/settings/token/revoke/<token_id>', methods=['POST'])
@login_required
def revoke_api_user_token(token_id):
    """ Revoke a user token (ie: not project specific).
    """
    if admin_session_timedout():
        flask.flash('Action canceled, try it again', 'error')
        url = flask.url_for('.user_settings')
        return flask.redirect(
            flask.url_for('auth_login', next=url))

    token = pagure.lib.get_api_token(flask.g.session, token_id)

    if not token \
            or token.user.username != flask.g.fas_user.username:
        flask.abort(404, 'Token not found')

    form = pagure.forms.ConfirmationForm()

    if form.validate_on_submit():
        try:
            if token.expiration >= datetime.datetime.utcnow():
                token.expiration = datetime.datetime.utcnow()
                flask.g.session.add(token)
            flask.g.session.commit()
            flask.flash('Token revoked')
        except SQLAlchemyError as err:  # pragma: no cover
            flask.g.session.rollback()
            _log.exception(err)
            flask.flash(
                'Token could not be revoked, please contact an admin',
                'error')

    return flask.redirect(flask.url_for('ui_ns.user_settings'))
