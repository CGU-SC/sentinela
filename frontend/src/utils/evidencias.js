/** Apresentação dos itens da cesta de evidências (painel, /listas, Cronologia). */

export const TIPO_EVIDENCIA = Object.freeze({
  dia: { label: 'Dia', icon: 'pi-calendar' },
  hora: { label: 'Hora', icon: 'pi-clock' },
  autorizacao: { label: 'Autorização', icon: 'pi-ticket' },
});

export const TIPO_EVIDENCIA_OPCOES = Object.freeze([
  { value: null, label: 'Todos' },
  { value: 'dia', label: 'Dias' },
  { value: 'hora', label: 'Horas' },
  { value: 'autorizacao', label: 'Autorizações' },
]);

export function tipoEvidencia(tipo) {
  const info = TIPO_EVIDENCIA[tipo];
  if (!info) throw new Error(`Tipo de evidência desconhecido: ${tipo}`);
  return info;
}

function dataBr(isoDate) {
  const [ano, mes, dia] = String(isoDate).slice(0, 10).split('-');
  return `${dia}/${mes}/${ano}`;
}

function horaLabel(hora) {
  return `${String(hora).padStart(2, '0')}h`;
}

/** "29/01/2021", "29/01/2021 · 11h" ou "29/01/2021 · 11:10:32". */
export function quandoEvidencia(ev) {
  const data = dataBr(ev.dt_janela);
  if (ev.tipo === 'dia') return data;
  if (ev.tipo === 'hora') return `${data} · ${horaLabel(ev.hora)}`;
  return `${data} · ${ev.snapshot?.horario || horaLabel(ev.hora)}`;
}

function autorizacoesTexto(qtd) {
  if (qtd === null || qtd === undefined) return null;
  const n = Number(qtd);
  return `${n.toLocaleString('pt-BR')} autorizaç${n === 1 ? 'ão' : 'ões'}`;
}

const moeda = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });

/** Resumo em uma linha, montado a partir do retrato salvo no momento da marcação. */
export function resumoEvidencia(ev) {
  const s = ev.snapshot ?? {};
  const alertas = Array.isArray(s.alertas) && s.alertas.length ? s.alertas.join(', ') : null;
  if (ev.tipo === 'autorizacao') {
    return [
      `Nº ${ev.num_autorizacao}`,
      s.crm ? `CRM ${s.crm}` : null,
      s.medico || null,
      s.valor !== null && s.valor !== undefined ? moeda.format(Number(s.valor)) : null,
      alertas,
    ].filter(Boolean).join(' · ');
  }
  return [autorizacoesTexto(s.qtd), alertas].filter(Boolean).join(' · ') || '—';
}

/** Rótulos dos alertas de um dia ou de uma hora da Cronologia. */
export function alertasDaJanela(janela) {
  if (!janela) return [];
  const alertas = [];
  if (janela.is_volume_horario_anomalo === 1) alertas.push('Volume Atípico');
  if (janela.is_crm_unico === 1) alertas.push('Sequência · Único CRM');
  if (janela.is_crm_multiplo === 1) alertas.push('Sequência · Múltiplos CRMs');
  return alertas;
}

export function dataHoraCurta(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' });
}
