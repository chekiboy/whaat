# Reports

The reports module collects every document the agents wrote into one list: journals, session reports and curation reports, from every identity. You use it to read what happened and to decide what waits for you.

## Where reports come from

- **An identity's own folder:** its journal entries, session reports and curation reports. These are private to that identity and the admin.
- **Shared folders** you name in the `WHAAT_SHARED_REPORTS` setting, for reports other tools write, such as code reviews or investigations. These can be markdown or JSON.

A report that names another identity than the folder it sits in still belongs to its folder's owner; the app shows a warning on it.

## Reading them

The **Reports** page lists them side by side. You can filter by kind and by whose they are. Each kind has its own view:
- a **session report** shows the task, the steps, the decisions and the drift, with that session's journal entry beside it;
- a **curation report** shows each proposed change with a small diagram of what it would do, and buttons to apply, reject, add a note or revert (see [Curation](curation.md));
- a **markdown report** is shown as written.

A report's address in the app is a short code, so a link does not reveal what it opens.

## Commands

| Command | What it does |
|---|---|
| `whaat open <report id>` | Opens a report in the app, starting the server if needed |
| `whaat show <report id>` | Prints a report as JSON, as the calling identity sees it |
