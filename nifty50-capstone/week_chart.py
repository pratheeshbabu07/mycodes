"""The weekly prediction chart, as one reusable figure builder.

Extracted from Predict_Future_N50_Opening.py so the batch script and the web API draw
the identical picture. Returns a figure and never shows or saves it - the caller
decides, because the API needs a PNG on disk while the script also wants a window.
"""

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# Light-surface tokens. Hue carries direction (Up/Down); lightness within that hue
# carries horizon (already traded vs still to come), with a hatch on past bars so
# the distinction survives in greyscale.
SURFACE = '#fcfcfb'
INK, INK_SOFT, INK_MUTED = '#0b0b0b', '#52514e', '#6e6a65'
GRIDLINE, BASELINE = '#e1e0d9', '#c3c2b7'
BAR_COLORS = {
    ('Up',   True):  '#0ca30c',   # forecast, full strength
    ('Down', True):  '#d03b3b',
    ('Up',   False): '#84cf83',   # already traded, same hue lightened
    ('Down', False): '#e69b9b',
}


def build_week_chart(df_predictions, target_days, today, weekend_run):
    """Figure for one week of predictions.

    df_predictions needs Date, Day, Horizon, Predicted Probability and
    Nifty 50 Open Direction columns - the frame the prediction run produces.
    """
    # Bars are drawn one at a time so each can carry its own direction hue and
    # horizon treatment. (It also sidesteps seaborn's hue+dodge=False patch
    # ordering, which does not follow row order.)
    fig, ax = plt.subplots(figsize=(10, 5.6), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)

    for x_pos, (_, row) in enumerate(df_predictions.iterrows()):
        direction = row['Nifty 50 Open Direction']
        is_forecast = row['Horizon'] == 'Forecast'
        colour = BAR_COLORS[(direction, is_forecast)]
        ax.bar(x_pos, row['Predicted Probability'], width=0.62,
               color=colour, zorder=3,
               # Hatch on past bars keeps the horizon readable without colour
               hatch=None if is_forecast else '///',
               edgecolor=BAR_COLORS[(direction, True)], linewidth=0)
        # Direction spelled out, so it never rests on hue alone
        ax.text(x_pos, row['Predicted Probability'] + 0.015, direction,
                ha='center', va='bottom', fontsize=9.5,
                color=INK if is_forecast else INK_MUTED,
                fontweight='semibold' if is_forecast else 'normal', zorder=4)

    n = len(df_predictions)
    n_past = int((df_predictions['Horizon'] == 'Already traded').sum())

    # Divider between what has traded and what is still a forecast
    if 0 < n_past < n:
        ax.axvline(n_past - 0.5, color=BASELINE, linewidth=1, zorder=2)
        ax.text(n_past - 0.42, 1.015, 'forecast from here',
                ha='left', va='bottom', fontsize=9, color=INK_SOFT, zorder=4)

    # The model's own 50% decision boundary - a real threshold, hence dashed.
    # It is explained in the subtitle rather than labelled in place: a bar
    # sitting near 0.5 leaves nowhere to put the caption without a collision.
    ax.axhline(0.5, color=INK_MUTED, linewidth=1, linestyle=(0, (4, 3)), zorder=2)

    ax.set_ylim(0, 1.09)
    ax.set_xlim(-0.7, n - 0.3)
    ax.set_xticks(range(n))
    ax.set_xticklabels([f"{r['Day']}\n{r['Date'][5:]}" for _, r in df_predictions.iterrows()],
                       fontsize=9.5, color=INK_SOFT)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.tick_params(axis='both', length=0, colors=INK_MUTED)
    ax.set_ylabel('Probability of an up open', fontsize=10, color=INK_SOFT)
    ax.set_xlabel('')

    # Recessive chrome: hairline horizontal grid, no box
    ax.grid(axis='y', color=GRIDLINE, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    for side in ('top', 'right', 'left'):
        ax.spines[side].set_visible(False)
    ax.spines['bottom'].set_color(BASELINE)

    # Header is placed in FIGURE coordinates, not axes coordinates. In axes
    # coords the title's position depends on the axes height, so it drifted
    # off the top of the canvas; pinned to the figure it always sits inside
    # the window, and the margins below reserve the room it needs.
    week_of = f"{target_days[0]:%d %b} - {target_days[-1]:%d %b %Y}"
    subtitle = (f"Week of {week_of}   ·   run {today:%a %d %b}"
                + ("   ·   market shut, whole week is forecast" if weekend_run else "")
                + "\nDashed line is the model's 50% decision threshold - "
                  "bars above it open Up, below it Down")
    # Both anchored from their top, so a subtitle that grows to two lines
    # pushes downward into the gap rather than up into the title.
    fig.text(0.085, 0.965, 'Nifty 50 predicted open direction',
             fontsize=14.5, color=INK, va='top', fontweight='semibold')
    fig.text(0.085, 0.895, subtitle,
             fontsize=9.5, color=INK_MUTED, va='top', linespacing=1.5)

    legend_handles = [
        mpatches.Patch(facecolor=BAR_COLORS[('Up', True)], label='Up - forecast'),
        mpatches.Patch(facecolor=BAR_COLORS[('Down', True)], label='Down - forecast'),
        mpatches.Patch(facecolor=BAR_COLORS[('Up', False)], hatch='///',
                       edgecolor=BAR_COLORS[('Up', True)], linewidth=0,
                       label='Up - already traded'),
        mpatches.Patch(facecolor=BAR_COLORS[('Down', False)], hatch='///',
                       edgecolor=BAR_COLORS[('Down', True)], linewidth=0,
                       label='Down - already traded'),
    ]
    # Legend sits below the plot so it cannot collide with the divider note
    legend = ax.legend(handles=legend_handles, ncol=4, frameon=False,
                       loc='upper center', bbox_to_anchor=(0.5, -0.13),
                       fontsize=9, handlelength=1.4, handleheight=1.1,
                       columnspacing=1.8)
    for text in legend.get_texts():
        text.set_color(INK_SOFT)

    # Margins reserve the header above and the tick labels + legend below, so
    # everything fits the canvas as drawn. Saved WITHOUT bbox_inches='tight':
    # tight cropping grows the canvas at save time, which made the PNG look
    # right while the interactive window was still clipping the title.
    fig.subplots_adjust(left=0.085, right=0.975, top=0.775, bottom=0.185)
    return fig


def save_week_chart(df_predictions, target_days, today, weekend_run, path):
    """Render the chart straight to `path`. Used by the server, which has no display."""
    # The server runs with no GUI, so force the file backend before a figure exists.
    matplotlib.use('Agg', force=False)
    fig = build_week_chart(df_predictions, target_days, today, weekend_run)
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return path
