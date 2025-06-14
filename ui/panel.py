import marimo

__generated_with = "0.13.4"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _():
    import ouscope
    from ouscope.core import Telescope
    from ouscope.vs import submitVarStar
    from collections import namedtuple
    import configparser
    import os
    import logging
    from os.path import expanduser
    import argparse
    return Telescope, configparser, expanduser, namedtuple


@app.cell
def _(configparser, expanduser):
    config = configparser.ConfigParser()
    config.read(expanduser('~/.config/telescope.ini'))
    args_verbose = True
    args_quiet = False
    return args_quiet, args_verbose, config


@app.cell
def _(namedtuple):
    VStar=namedtuple('VStar', 'name comm expos')
    return (VStar,)


@app.cell
def _(args_quiet, args_verbose):
    def qprint(*ar, **kwar):
        if not args_quiet:
            print(*ar, **kwar)

    def vprint(*ar, **kwar):
        if args_verbose and not args_quiet:
            print(*ar, **kwar)

    return (qprint,)


@app.cell
def _(VStar):
    obslst={_vs.name:_vs for _vs in 
        [#VStar('S Ori', comm='Mira AAVSO', expos=120),
        VStar('V1223 Sgr', comm='AAVSO', expos=180),
        VStar('CH Cyg', comm='Symbiotic AAVSO', expos=60),
        VStar('SS Cyg', comm='Mira', expos=180),
        #VStar('EU Cyg', comm='Mira', expos=180),
        VStar('IP Cyg', comm='Mira', expos=180),
        VStar('V686 Cyg', comm='Mira', expos=180),
        #VStar('AS Lac', comm='Mira', expos=120),
        VStar('BI Her', comm='Mira', expos=180),
        VStar('DX Vul', comm='Mira', expos=180),
        VStar('DQ Vul', comm='Mira', expos=180),
        VStar('EQ Lyr', comm='Mira', expos=180),
        VStar('LX Cyg', comm='AAVSO', expos=180),
        ]}
    return (obslst,)


@app.cell
def _(Telescope, config):
    scope=Telescope(config['telescope.org']['user'], config['telescope.org']['password'])
    return (scope,)


@app.cell
def _(mo, req_refresh, scope, set_reqlst):
    mo.stop(not req_refresh.value)

    set_reqlst(scope.get_user_requests(sort='completion'))
    return


@app.cell
def _(mo, scope):
    get_reqlst, set_reqlst = mo.state(scope.get_user_requests(sort='completion'))
    return get_reqlst, set_reqlst


@app.cell
def _(get_reqlst, mo):
    q=[r for r in get_reqlst() if int(r['status'])<8]
    get_queue, set_queue = mo.state([r['objectname'] for r in q])
    return get_queue, set_queue


@app.cell
def _(mo):
    req_refresh = mo.ui.run_button(label='Refresh request list')
    req_refresh
    return (req_refresh,)


@app.cell
def _(mo, scope, submit_button, submit_selected_jobs):
    # if the button hasn't been clicked, don't run.
    mo.stop(not submit_button.value)
    submit_selected_jobs(scope)
    return


@app.cell
def _(get_reqlst, mo, queue_control):
    mo.ui.tabs({
        'Queue': queue_control,
        'New': mo.ui.table([_r for _r in get_reqlst() if int(_r['status'])>=8 and not int(_r['seen']) ]),
        'Not ready': mo.ui.table([_r for _r in get_reqlst() if int(_r['status'])<8]),
        'Ready': mo.ui.table([_r for _r in get_reqlst() if int(_r['status'])>=8]), 
        'All requests': mo.ui.table(get_reqlst()),
    })
    return


@app.cell
def _(get_reqlst):
    objects = {r['objectname'] for r in get_reqlst()}
    return


@app.cell
def _(left_side, mo, right_side, submit_button):
    # Define a vertical separator using HTML
    separator = mo.Html("<div style='border-left: 1px solid #ccc; margin: 0 20px; height: 100%;'></div>")

    # Combine the left side elements (checkboxes) and the button vertically
    left_panel = mo.vstack([left_side, submit_button], align='start')

    # Combine the left panel, separator, and reactive right side using hstack
    queue_control = mo.hstack([left_panel, separator, right_side], widths=[0.45, 0.1, 0.45])
    return (queue_control,)


@app.cell
def _(mo):
    # Create the run button that executes the submission function cell
    # The button doesn't need an on_click handler; its action is defined by its cell placement
    submit_button = mo.ui.run_button(label="Submit Selected Jobs")
    return (submit_button,)


@app.cell
def _(get_queue, mo):
    # This cell reactively displays the current queue
    # It re-executes whenever the 'qn' list changes
    right_side = mo.md(
        "### Current Queue:\n\n" + "\n".join([f"- {name}" for name in get_queue()])
    )
    return (right_side,)


@app.cell
def _(get_queue, mo, obslst):
    vstar_checkboxes = []

    for _nm, _vs in obslst.items():
        # Check if the star's name is now in the queue 
        is_in_queue = _vs.name in get_queue()

        if is_in_queue:
            # If the star is in the queue, display it as simple text (disabled state)
            disabled_label = mo.md(f'___ {_vs.name}')
            # Add attributes to simulate checkbox api
            disabled_label.name = _vs.name
            disabled_label.value = False
            vstar_checkboxes.append(disabled_label)
        else:
            # If the star is not in the queue, create a selectable checkbox
            checkbox = mo.ui.checkbox(
                label=_vs.name, # The label is used here for display
                value=False
            )

            # Add atribute to index into obslst
            checkbox.name = _vs.name

            # Add the checkbox element to the list for display
            vstar_checkboxes.append(checkbox)

    # Display the elements as part of the left panel
    left_side = mo.vstack([mo.md("### Select stars to add to queue:")] + vstar_checkboxes, align='start')
    return left_side, vstar_checkboxes


@app.cell
def _(get_queue, obslst, qprint, set_queue, vstar_checkboxes):
    # Cell to define the submission function
    # This function will be executed by the run button
    def submit_selected_jobs(_scope):
        submitted_count = 0
        # Iterate through the stored pairs of (VStar object, checkbox)
        for cb in vstar_checkboxes:
            if cb.value:
                # If the checkbox is checked, use the associated VStar object
                qprint(f"Submitting {cb.name}...")
                try:
                    vstar_to_submit = obslst[cb.name]
                    qprint(f"Submitting {vstar_to_submit}")
                    # Call the actual submission function using info from the VStar object
                    r, i = _scope.submitVarStar(name = vstar_to_submit.name, 
                                               comm = vstar_to_submit.comm, 
                                               expos = vstar_to_submit.expos)
                    if r :
                        qprint(f"Successfully submitted {cb.name}")
                        qprint(f' => id: {i}', end='')
                        set_queue(get_queue() + [cb.name])
                        submitted_count += 1
                    else :
                        qprint(f' Failure: {i}', end='')                
                except Exception as e:
                    # Handle potential errors during submission
                    qprint(f"Error submitting {cb.name}: {e}")

        # # Optional: Provide feedback to the user
        if submitted_count > 0:
            qprint(f"Submitted {submitted_count} job(s).")
        else:
            qprint("No jobs selected for submission.")


    # The function itself doesn't need to return anything for display
    # Its purpose is the side effect (submitting jobs and modifying qn)
    return (submit_selected_jobs,)


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
