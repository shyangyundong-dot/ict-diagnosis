<template>
  <div class="field-control">
    <template v-if="fieldKey === 'project_type'">
      <div class="multi-checks">
        <label v-for="(opt, i) in (defn.options || [])" :key="String(opt)" class="check-line">
          <input
            type="checkbox"
            :checked="projectTypeList.includes(opt)"
            @change="toggleProjectType(opt, $event.target.checked)"
          />
          <span>{{ (defn.options_label || [])[i] }}</span>
        </label>
      </div>
    </template>
    <template v-else-if="fieldKey === 'bpm_id'">
      <input
        type="text"
        class="field-control-input"
        :value="modelValue ?? ''"
        placeholder="测试阶段可填任意编号"
        @change="(e) => emit('update:modelValue', e.target.value)"
      />
    </template>
    <template v-else-if="(defn.options || []).length">
      <select class="field-control-select" :value="selectIndex" @change="onSelect">
        <option value="" disabled>请选择</option>
        <option v-for="(opt, i) in defn.options" :key="i" :value="String(i)">
          {{ defn.options_label[i] }}
        </option>
      </select>
    </template>
    <template v-else>
      <span class="field-fallback">{{ modelValue }}</span>
    </template>
    <div v-if="defn.hint" class="hint-wrap">
      <span class="hint-icon">?</span>
      <span class="hint-tooltip">{{ defn.hint }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  fieldKey: { type: String, required: true },
  modelValue: { type: [String, Number, Boolean, Array, Object], default: undefined },
  definitions: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['update:modelValue'])

const defn = computed(() => props.definitions[props.fieldKey] || {})

const projectTypeList = computed(() => {
  const v = props.modelValue
  if (Array.isArray(v)) return v
  if (typeof v === 'string' && v) return [v]
  return []
})

function toggleProjectType(val, checked) {
  const arr = [...projectTypeList.value]
  if (checked) {
    if (!arr.includes(val)) arr.push(val)
  } else {
    const j = arr.indexOf(val)
    if (j >= 0) arr.splice(j, 1)
  }
  emit('update:modelValue', arr)
}

const selectIndex = computed(() => {
  const opts = defn.value.options || []
  const i = opts.indexOf(props.modelValue)
  return i >= 0 ? String(i) : ''
})

function onSelect(ev) {
  const idx = parseInt(ev.target.value, 10)
  if (ev.target.value === '' || Number.isNaN(idx)) return
  const raw = defn.value.options[idx]
  emit('update:modelValue', raw)
}
</script>

<style scoped>
.multi-checks {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.check-line {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--slate-800);
  cursor: pointer;
}
.check-line input {
  accent-color: var(--blue-600);
}
.field-control-input {
  width: 100%;
  box-sizing: border-box;
  padding: 8px 10px;
  border: 1px solid var(--slate-200);
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-family: inherit;
}
.field-control-input:focus {
  outline: none;
  border-color: var(--blue-500);
}
.field-control-select {
  width: 100%;
  box-sizing: border-box;
  padding: 8px 10px;
  border: 1px solid var(--slate-200);
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-family: inherit;
  background: #fff;
  cursor: pointer;
}
.field-control-select:focus {
  outline: none;
  border-color: var(--blue-500);
}
.field-fallback {
  font-size: 13px;
  color: var(--slate-600);
  word-break: break-word;
}
.hint-wrap {
  position: relative;
  display: inline-flex;
  align-items: center;
  margin-top: 5px;
}
.hint-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--slate-300);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  cursor: default;
  user-select: none;
  line-height: 1;
}
.hint-tooltip {
  display: none;
  position: absolute;
  left: 22px;
  top: 50%;
  transform: translateY(-50%);
  background: #1e293b;
  color: #fff;
  font-size: 12px;
  line-height: 1.6;
  padding: 8px 12px;
  border-radius: 6px;
  width: 240px;
  z-index: 100;
  white-space: pre-wrap;
  box-shadow: 0 4px 12px rgba(0,0,0,0.2);
}
.hint-wrap:hover .hint-tooltip {
  display: block;
}
</style>
