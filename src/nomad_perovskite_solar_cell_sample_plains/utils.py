#
# Copyright The NOMAD Authors.
#
# This file is part of NOMAD. See https://nomad-lab.eu for further info.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import numpy as np
import plotly.graph_objects as go

# Wavelength [nm] of a photon of energy 1 eV -- h*c in eV*nm.
_EV_NM = 1239.841984

# Below this many points a line is invisible, so the markers are drawn as well.
_SHORT_TRACK = 3


def get_reference(upload_id, entry_id):
    return f'../uploads/{upload_id}/archive/{entry_id}#data'


def get_entry_id_from_file_name(file_name, archive):
    from nomad.utils import hash

    return hash(archive.metadata.upload_id, file_name)


def create_archive(entity, archive, file_name) -> str:
    import json

    from nomad.datamodel.context import ClientContext

    if isinstance(archive.m_context, ClientContext):
        return None
    if not archive.m_context.raw_path_exists(file_name):
        entity_entry = entity.m_to_dict(with_root_def=True)
        with archive.m_context.raw_file(file_name, 'w') as outfile:
            json.dump({'data': entity_entry}, outfile)
        archive.m_context.process_updated_raw_file(file_name)
    return get_reference(
        archive.metadata.upload_id, get_entry_id_from_file_name(file_name, archive)
    )


def add_cuboid_edges(fig, x0, x1, y0, y1, z0, z1):  # noqa: PLR0913
    """
    Creates a Scatter3d trace with lines connecting the cuboid's edges
    and adds it to 'fig' to provide a wireframe look.
    """
    corners = [
        (x0, y0, z0),  # 0
        (x0, y1, z0),  # 1
        (x1, y1, z0),  # 2
        (x1, y0, z0),  # 3
        (x0, y0, z1),  # 4
        (x0, y1, z1),  # 5
        (x1, y1, z1),  # 6
        (x1, y0, z1),  # 7
    ]
    edges = [
        (0, 1),
        (1, 2),
        (2, 3),
        (3, 0),  # bottom face
        (4, 5),
        (5, 6),
        (6, 7),
        (7, 4),  # top face
        (0, 4),
        (1, 5),
        (2, 6),
        (3, 7),  # verticals
    ]

    edge_x, edge_y, edge_z = [], [], []
    for start_i, end_i in edges:
        (xs, ys, zs) = corners[start_i]
        (xe, ye, ze) = corners[end_i]
        # Add the start/end of each edge plus None to break the line
        edge_x.extend([xs, xe, None])
        edge_y.extend([ys, ye, None])
        edge_z.extend([zs, ze, None])

    # Add lines for edges
    fig.add_trace(
        go.Scatter3d(
            x=edge_x,
            y=edge_y,
            z=edge_z,
            mode='lines',
            line=dict(color='black', width=3),
            showlegend=False,
            hoverinfo='skip',
        )
    )


def format_device_parameter(value, suffix=''):
    """
    Formats a single device parameter for the annotation box.

    Missing values render as 'N/A' so that a device without (complete) JV data still
    gets a stack figure instead of raising a TypeError.
    """
    if value is None:
        return 'N/A'
    magnitude = getattr(value, 'magnitude', value)
    return f'{magnitude:.1f}{suffix}'


def create_cell_stack_figure(  # noqa: PLR0913
    layers,
    thicknesses,
    colors,
    efficiency,
    voc,
    jsc,
    ff,
    x_min=0,
    x_max=10,
    y_min=0,
    y_max=10,
):
    """
    Builds and returns a Plotly 3D figure showing the device stack.

    :param layers: list of layer names (top to bottom or bottom to top)
    :param thicknesses: list of thickness values corresponding to each layer
    :param colors: list of colors (one per layer)
    :param efficiency: device efficiency (%)
    :param voc: open-circuit voltage
    :param jsc: short-circuit current
    :param ff: fill factor
    :param x_min, x_max, y_min, y_max: 2D footprint of each layer
    :return: A Plotly Figure object
    """
    fig = go.Figure()

    z_current = 0
    for layer_name, thickness, color in zip(layers, thicknesses, colors):
        z0 = z_current
        z1 = z_current + thickness

        # 8 corner points for Mesh3d
        x_corners = [x_min, x_min, x_min, x_min, x_max, x_max, x_max, x_max]
        y_corners = [y_min, y_min, y_max, y_max, y_min, y_min, y_max, y_max]
        z_corners = [z0, z1, z0, z1, z0, z1, z0, z1]

        # Add the cuboid block
        fig.add_trace(
            go.Mesh3d(
                x=x_corners,
                y=y_corners,
                z=z_corners,
                color=color,
                alphahull=1,
                name=layer_name,
                showlegend=True,
                hoverinfo='name',
            )
        )

        # Add black wireframe around this cuboid
        add_cuboid_edges(fig, x_min, x_max, y_min, y_max, z0, z1)

        z_current = z1

    # Create an annotation for device parameters
    annotation_text = (
        f'<b>Device Parameters</b><br>'
        f'Efficiency = {format_device_parameter(efficiency, " %")}<br>'
        f'V<sub>OC</sub> = {format_device_parameter(voc)}<br>'
        f'J<sub>SC</sub> = {format_device_parameter(jsc)}<br>'
        f'FF = {format_device_parameter(None if ff is None else ff * 100, " %")}'
    )

    # Update layout
    fig.update_layout(
        hovermode='closest',
        legend=dict(x=0.0, y=1.0, xanchor='left', yanchor='top', traceorder='reversed'),
        scene=dict(
            xaxis=dict(visible=False, showgrid=False, zeroline=False),
            yaxis=dict(visible=False, showgrid=False, zeroline=False),
            zaxis=dict(visible=False, showgrid=False, zeroline=False),
            camera=dict(eye=dict(x=1.75, y=1.75, z=1.25)),
            dragmode='turntable',
        ),
        width=800,
        height=600,
        margin=dict(r=10, l=10, b=10, t=50),
        showlegend=True,
        annotations=[
            go.layout.Annotation(
                text=annotation_text,
                align='left',
                showarrow=False,
                x=1.0,
                y=1.0,
                xref='paper',
                yref='paper',
                xanchor='right',
                yanchor='top',
                borderwidth=0,
            )
        ],
    )

    return fig


# ── Overview figures ─────────────────────────────────────────────────────────
#
# One figure per measurement kind, holding *every* measurement of that kind made
# on the sample. The measurement entries themselves each plot their own single
# run; these combine them, so a device can be read in one place.


def to_array(value, unit=None):
    """A plain float array from a metainfo quantity, or None if there is nothing to plot.

    Array quantities come back as pint quantities; `unit` states the unit the
    figure works in, so a track in seconds and one in hours end up on the same
    axis.
    """
    if value is None:
        return None
    if unit is not None and hasattr(value, 'to'):
        value = value.to(unit)
    magnitude = getattr(value, 'magnitude', value)
    array = np.asarray(magnitude, dtype=np.float64).ravel()
    if array.size == 0 or not np.any(np.isfinite(array)):
        return None
    return array


def to_scalar(value, unit=None):
    """A plain float from a metainfo quantity, or None."""
    if value is None:
        return None
    if unit is not None and hasattr(value, 'to'):
        value = value.to(unit)
    magnitude = getattr(value, 'magnitude', value)
    try:
        return float(magnitude)
    except (TypeError, ValueError):
        return None


def _measurement_name(measurement, fallback):
    return str(getattr(measurement, 'name', None) or fallback)


def _hover(title, lines, axes):
    """A hovertemplate: the trace's fixed facts, then the point under the cursor."""
    facts = ''.join(f'{line}<br>' for line in lines if line)
    return f'<b>{title}</b><br>{facts}{axes}<extra></extra>'


def _statistics_annotation(statistics):
    """The best / worst / average KPI box drawn onto the JV overview."""

    def row(label, values, digits=2, factor=1.0):
        if any(value is None for value in values):
            return None
        formatted = ' / '.join(f'{value * factor:.{digits}f}' for value in values)
        return f'{label}: {formatted}'

    def kpi(prefix, unit=None):
        return [
            to_scalar(getattr(statistics, f'{prefix}_{which}'), unit)
            for which in ('best', 'average', 'worst')
        ]

    rows = [
        f'<b>best / average / worst over {statistics.number_of_jv_scans} scans</b>',
        row('PCE (%)', kpi('pce')),
        row('V<sub>OC</sub> (V)', kpi('voc', 'V'), digits=3),
        row('J<sub>SC</sub> (mA/cm²)', kpi('jsc', 'mA/cm**2')),
        row('FF (%)', kpi('ff'), digits=1, factor=100.0),
    ]
    return '<br>'.join(row for row in rows if row)


def create_jv_overview_figure(measurements, statistics=None):
    """Every JV curve measured on this sample, in one plot.

    Returns None when there is nothing to draw, so the caller can leave the
    figure out entirely rather than showing an empty one.
    """
    fig = go.Figure()
    drawn = 0

    for index, measurement in enumerate(measurements):
        source = _measurement_name(measurement, f'JV {index + 1}')
        for curve in getattr(measurement, 'jv_curve', None) or []:
            voltage = to_array(curve.voltage, 'V')
            current_density = to_array(curve.current_density, 'mA/cm**2')
            if voltage is None or current_density is None:
                continue
            if len(voltage) != len(current_density):
                continue

            name = str(getattr(curve, 'cell_name', None) or 'Cell')
            dark = bool(getattr(curve, 'dark', False))
            efficiency = to_scalar(curve.efficiency)
            voc = to_scalar(curve.open_circuit_voltage, 'V')
            jsc = to_scalar(curve.short_circuit_current_density, 'mA/cm**2')
            ff = to_scalar(curve.fill_factor)

            facts = [
                'dark scan' if dark else None,
                None if efficiency is None else f'PCE = {efficiency:.2f} %',
                None if voc is None else f'V<sub>OC</sub> = {voc:.3f} V',
                None if jsc is None else f'J<sub>SC</sub> = {jsc:.2f} mA/cm²',
                None if ff is None else f'FF = {ff * 100:.1f} %',
            ]

            fig.add_trace(
                go.Scatter(
                    x=voltage,
                    y=current_density,
                    mode='lines',
                    name=name,
                    legendgroup=source,
                    legendgrouptitle_text=source,
                    line=dict(dash='dot', color='#909090') if dark else None,
                    hovertemplate=_hover(
                        f'{source} · {name}',
                        facts,
                        'V = %{x:.3f} V<br>J = %{y:.2f} mA/cm²',
                    ),
                )
            )
            drawn += 1

    if not drawn:
        return None

    annotations = []
    if statistics is not None:
        text = _statistics_annotation(statistics)
        if text:
            annotations.append(
                go.layout.Annotation(
                    text=text,
                    align='left',
                    showarrow=False,
                    x=0.02,
                    y=0.02,
                    xref='paper',
                    yref='paper',
                    xanchor='left',
                    yanchor='bottom',
                    bgcolor='rgba(255, 255, 255, 0.8)',
                    bordercolor='#909090',
                    borderwidth=1,
                    borderpad=6,
                )
            )

    fig.update_layout(
        title='JV curves — all measurements of this sample',
        xaxis_title='Voltage (V)',
        yaxis_title='Current density (mA/cm²)',
        template='plotly_white',
        hovermode='closest',
        annotations=annotations,
    )
    fig.update_xaxes(zeroline=True, zerolinecolor='#c0c0c0')
    fig.update_yaxes(zeroline=True, zerolinecolor='#c0c0c0')
    return fig


def create_stability_overview_figure(measurements):
    """Every MPP track measured on this sample, in one plot.

    The tracked efficiency is drawn as a line. Where the run also sampled JV
    curves along the way (the CHOSE stability export does), those are drawn as
    markers on the same axes -- which is the only thing there is to see when the
    track itself is a single point.
    """
    fig = go.Figure()
    drawn = 0

    for index, measurement in enumerate(measurements):
        source = _measurement_name(measurement, f'MPP track {index + 1}')

        time = to_array(getattr(measurement, 'time', None), 'hour')
        efficiency = to_array(getattr(measurement, 'efficiency', None))
        if time is not None and efficiency is not None and len(time) == len(efficiency):
            fig.add_trace(
                go.Scatter(
                    x=time,
                    y=efficiency,
                    mode='lines+markers' if len(time) < _SHORT_TRACK else 'lines',
                    name='MPP track',
                    legendgroup=source,
                    legendgrouptitle_text=source,
                    hovertemplate=_hover(
                        source, [], 't = %{x:.2f} h<br>PCE = %{y:.2f} %'
                    ),
                )
            )
            drawn += 1

        parameters = getattr(measurement, 'jv_parameters', None)
        if parameters is None:
            continue
        # The parameter series already carries its own time axis, in hours.
        parameter_time = to_array(getattr(parameters, 'time', None), 'hour')
        if parameter_time is None:
            continue
        for attribute, label in (
            ('efficiency_fw', 'JV forward'),
            ('efficiency_rv', 'JV reverse'),
        ):
            values = to_array(getattr(parameters, attribute, None))
            if values is None:
                continue
            points = min(len(parameter_time), len(values))
            fig.add_trace(
                go.Scatter(
                    x=parameter_time[:points],
                    y=values[:points],
                    mode='markers',
                    name=label,
                    legendgroup=source,
                    legendgrouptitle_text=source,
                    hovertemplate=_hover(
                        f'{source} · {label}',
                        [],
                        't = %{x:.2f} h<br>PCE = %{y:.2f} %',
                    ),
                )
            )
            drawn += 1

    if not drawn:
        return None

    fig.update_layout(
        title='MPP tracking — all measurements of this sample',
        xaxis_title='Time (h)',
        yaxis_title='Efficiency (%)',
        template='plotly_white',
        hovermode='closest',
    )
    return fig


def create_eqe_overview_figure(measurements):
    """Every EQE spectrum measured on this sample, in one plot."""
    fig = go.Figure()
    drawn = 0

    for index, measurement in enumerate(measurements):
        source = _measurement_name(measurement, f'EQE {index + 1}')
        spectra = getattr(measurement, 'eqe_data', None) or []

        for spectrum_index, spectrum in enumerate(spectra):
            eqe = to_array(getattr(spectrum, 'eqe_array', None))
            if eqe is None:
                continue

            wavelength = to_array(getattr(spectrum, 'wavelength_array', None), 'nm')
            if wavelength is None:
                # `wavelength_array` is derived in the spectrum's own normalize; a
                # spectrum that never ran it still states its photon energy.
                photon_energy = to_array(
                    getattr(spectrum, 'photon_energy_array', None), 'eV'
                )
                if photon_energy is None:
                    continue
                wavelength = _EV_NM / photon_energy
            if len(wavelength) != len(eqe):
                continue

            name = source if len(spectra) == 1 else f'{source} #{spectrum_index + 1}'
            bandgap = to_scalar(getattr(spectrum, 'bandgap_eqe', None), 'eV')
            integrated_jsc = to_scalar(
                getattr(spectrum, 'integrated_jsc', None), 'mA/cm**2'
            )
            facts = [
                None if bandgap is None else f'band gap = {bandgap:.3f} eV',
                None
                if integrated_jsc is None
                else f'integrated J<sub>SC</sub> = {integrated_jsc:.2f} mA/cm²',
            ]

            fig.add_trace(
                go.Scatter(
                    x=wavelength,
                    # The spectrum is stored as a fraction; the plot reads in percent.
                    y=eqe * 100.0,
                    mode='lines',
                    name=name,
                    hovertemplate=_hover(
                        name, facts, 'λ = %{x:.0f} nm<br>EQE = %{y:.1f} %'
                    ),
                )
            )
            drawn += 1

    if not drawn:
        return None

    fig.update_layout(
        title='EQE — all measurements of this sample',
        xaxis_title='Wavelength (nm)',
        yaxis_title='EQE (%)',
        template='plotly_white',
        hovermode='closest',
    )
    return fig


def create_uvvis_overview_figure(measurements):
    """Every UV-Vis transmittance spectrum of this substrate, in one plot.

    UV-Vis is a film-level measurement: the transmittance describes the whole
    substrate, not a single pixel. The spectrum lives on the baseclass's repeating
    `measurements` subsection (`wavelength` in nm, `intensity` carrying the
    transmittance in %).
    """
    fig = go.Figure()
    drawn = 0

    for index, measurement in enumerate(measurements):
        source = _measurement_name(measurement, f'UV-Vis {index + 1}')
        spectra = getattr(measurement, 'measurements', None) or []

        for spectrum_index, spectrum in enumerate(spectra):
            transmittance = to_array(getattr(spectrum, 'intensity', None))
            if transmittance is None:
                continue
            wavelength = to_array(getattr(spectrum, 'wavelength', None), 'nm')
            if wavelength is None or len(wavelength) != len(transmittance):
                continue

            name = source if len(spectra) == 1 else f'{source} #{spectrum_index + 1}'
            fig.add_trace(
                go.Scatter(
                    x=wavelength,
                    y=transmittance,
                    mode='lines',
                    name=name,
                    hovertemplate=_hover(
                        name, [], 'λ = %{x:.0f} nm<br>T = %{y:.1f} %'
                    ),
                )
            )
            drawn += 1

    if not drawn:
        return None

    fig.update_layout(
        title='UV-Vis — all transmittance spectra of this substrate',
        xaxis_title='Wavelength (nm)',
        yaxis_title='Transmittance (%)',
        template='plotly_white',
        hovermode='closest',
    )
    return fig
