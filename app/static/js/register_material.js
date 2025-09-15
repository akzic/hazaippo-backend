// app/static/js/register_material.js
/* eslint-disable no-console */

/**
 * register_material.js  (2025-06 rev2)
 *  - Gemini Flash v2.* の JSON スキーマに対応
 *  - size / quantity が数値でない場合は「認識不可」とモーダル表示
 */

document.addEventListener('DOMContentLoaded', () => {
  /* ───────────────────────── DOM 取得 ───────────────────────── */
  const $ = id => document.getElementById(id);

  const form             = $('registerMaterialForm');
  const materialType     = $('material_type');
  const woodTypeGroup    = $('wood_type_group');
  const boardTypeGroup   = $('board_material_type_group');
  const panelTypeGroup   = $('panel_type_group');
  const size3Input       = $('material_size_3');
  const imageInput       = $('image');
  const mPrefInput       = $('m_prefecture');
  const mCityInput       = $('m_city');
  const mAddrInput       = $('m_address');
  const cityDL           = $('city_options');
  const addrDL           = $('address_options');
  const debugData        = $('debugData');
  const delImgBtn        = $('deleteImageButton');
  const submitBtn        = $('submitButton');

  /* Camera modal */
  const cameraModal      = $('cameraModal');
  const cameraStream     = $('cameraStream');
  const captureBtn       = $('captureImageBtn');
  const startCamBtn      = $('startCameraButton');
  const closeCamBtn      = $('closeCamera');

  /* Selection modal */
  const selModal         = $('selectionModal');
  const selContent       = $('selectionContent');
  const closeSelBtn      = $('closeSelectionModal');

  /* Success modal & flash */
  const successModal     = $('successModal');
  const closeSucBtn      = $('closeSuccessModal');
  const generalError     = $('general-error');

  const dashboardURL     = form.dataset.dashboardUrl;

  /* 状態管理 */
  let stream       = null;
  let taskId       = null;
  let taskTimer    = null;
  let retries      = 0;
  const MAX_RETRY  = 5;

  /* AI 結果 */
  const aiResults = { preprocessed:{}, non_preprocessed:{} };

  /* ─────────────── ユーティリティ ─────────────── */

  const isNum = v => v !== '' && !isNaN(v);

  const logForm = () => {
    if(!debugData) return;
    debugData.textContent = JSON.stringify({
      material_type : materialType.value,
      subtype       : (
        materialType.value==='木材'   ? $('wood_type').value :
        materialType.value==='ボード材'? $('board_material_type').value :
        materialType.value==='パネル材'? $('panel_type').value : ''
      ),
      size_1        : $('material_size_1').value,
      size_2        : $('material_size_2').value,
      size_3        : $('material_size_3').value,
      quantity      : $('quantity').value,
      location      : {pref:mPrefInput.value, city:mCityInput.value, addr:mAddrInput.value},
      deadline      : $('form_deadline').value,
      exclude_we    : $('exclude_weekends').checked,
      note          : $('note').value,
      ai_pre        : aiResults.preprocessed,
      ai_raw        : aiResults.non_preprocessed
    },null,2);
  };

  const jsonFetch = url => fetch(url).then(r=>r.ok?r.json():Promise.reject(r));

  const parseJPAddr = loc=>{
    if(!loc) return null;
    loc = loc.replace(/^日本[、,]\s*/, '').replace(/〒\d{3}-\d{4}\s*/, '');
    const prefs=['北海道','青森県','岩手県','宮城県','秋田県','山形県','福島県','茨城県','栃木県','群馬県','埼玉県','千葉県','東京都','神奈川県','新潟県','富山県','石川県','福井県','山梨県','長野県','岐阜県','静岡県','愛知県','三重県','滋賀県','京都府','大阪府','兵庫県','奈良県','和歌山県','鳥取県','島根県','岡山県','広島県','山口県','徳島県','香川県','愛媛県','高知県','福岡県','佐賀県','長崎県','熊本県','大分県','宮崎県','鹿児島県','沖縄県'];
    const pref=prefs.find(p=>loc.startsWith(p));
    if(!pref) return null;
    const rest=loc.slice(pref.length).trim();
    const m=rest.match(/^(.+?[市区町村])\s*(.*)$/);
    return {prefecture:pref, city:m?m[1]:'', address:m?m[2]:rest};
  };

  /* ─────────────── 表示切替・バリデーション ─────────────── */

  const toggleSubtypes = ()=>{
    woodTypeGroup .style.display='none';
    boardTypeGroup.style.display='none';
    panelTypeGroup.style.display='none';
    if(materialType.value==='木材')      woodTypeGroup .style.display='';
    if(materialType.value==='ボード材')  boardTypeGroup.style.display='';
    if(materialType.value==='パネル材')  panelTypeGroup.style.display='';
    size3Input.placeholder = (materialType.value==='ボード材'||materialType.value==='パネル材')?'厚み (mm)':'';
    logForm();
  };

  const validateNumInput = e=>{
    const f=e.target,v=f.value;
    if(!v){f.setCustomValidity('');return;}
    if(!isNum(v)){f.setCustomValidity('半角数字のみ');return;}
    if(f.id==='quantity'){
      const n=+v; f.setCustomValidity(n<1||n>100?'数量は1〜100':'');
    }else{
      f.setCustomValidity(+v<=0?'0より大きい値を':'');
    }
  };

  /* ─────────────── 住所候補 API ─────────────── */

  const refreshCities = pref=>{
    if(!pref) return;
    jsonFetch(`/materials/get_cities/${encodeURIComponent(pref)}`)
      .then(d=>{ cityDL.innerHTML = (d.cities||[]).map(c=>`<option value="${c}">`).join(''); })
      .catch(()=>{cityDL.innerHTML='<option disabled>取得失敗</option>';});
  };

  const refreshAddr = (pref,city)=>{
    if(!pref||!city) return;
    jsonFetch(`/materials/get_addresses/${encodeURIComponent(pref)}/${encodeURIComponent(city)}`)
      .then(d=>{ addrDL.innerHTML = (d.addresses||[]).map(a=>`<option value="${a}">`).join(''); })
      .catch(()=>{addrDL.innerHTML='<option disabled>取得失敗</option>';});
  };

  /* ─────────────── 画像送信とタスク監視 ─────────────── */

  const sendImg = async file=>{
    submitBtn.disabled=true; submitBtn.textContent='処理中…';

    let coords={};
    try{
      coords = await new Promise((res,rej)=>{
        navigator.geolocation.getCurrentPosition(p=>res(p.coords),rej);
      });
    }catch{/* ignore */}

    const fd=new FormData();
    fd.append('image',file);
    if(coords.latitude)  fd.append('latitude',coords.latitude);
    if(coords.longitude) fd.append('longitude',coords.longitude);

    const r = await fetch('/camera_ai/process_image',{method:'POST',body:fd});
    const j = await r.json().catch(()=>({status:'error'}));
    if(r.ok && j.status==='success'){
      taskId=j.task_id; retries=0;
      taskTimer=setInterval(checkTask,2000);
    }else{
      generalError.textContent=j.message||'画像送信に失敗';
      generalError.style.display='block';
      submitBtn.disabled=false; submitBtn.textContent='登録';
    }
  };

  const checkTask = async ()=>{
    const r=await fetch(`/camera_ai/task_status/${taskId}`);
    if(!r.ok){ if(++retries>=MAX_RETRY) clearInterval(taskTimer); return;}
    const d=await r.json();
    if(d.status==='pending'){ if(++retries>=MAX_RETRY) clearInterval(taskTimer); return; }

    clearInterval(taskTimer);
    if(d.status==='success'){
      aiResults.preprocessed     = d.preprocessed;
      aiResults.non_preprocessed = d.non_preprocessed;
      showSelModal();
    }else{
      alert(`AI解析失敗: ${d.message||''}`);
    }
    submitBtn.disabled=false; submitBtn.textContent='登録';
  };

  /* ─────────────── モーダル表示 ─────────────── */

  const resultRow = (label,val,needNum=false)=>{
    const disp = needNum ? (isNum(val)?val:'認識不可') : (val||'認識不可');
    return `<p><strong>${label}：</strong> ${disp}</p>`;
  };

  const buildHTML = (res,label)=>{
    if(!res) return '';
    return `
      <div class="result-section mb-4">
        <h4>${label} の結果</h4>
        ${resultRow('資材の種類',res.material_type)}
        ${res.subtype?resultRow('サブタイプ',res.subtype):''}
        ${resultRow('サイズ１',res.size_1,true)}
        ${resultRow('サイズ２',res.size_2,true)}
        ${resultRow('サイズ３',res.size_3,true)}
        ${resultRow('数量',   res.quantity,true)}
        ${res.location?resultRow('位置情報',res.location):''}
        <button class="btn btn-primary select-result-btn"
                data-type="${label==='前処理あり'?'preprocessed':'non_preprocessed'}">
          この結果を選択
        </button>
      </div>`;
  };

  const showSelModal = ()=>{
    selContent.innerHTML = buildHTML(aiResults.preprocessed,'前処理あり')
                        + buildHTML(aiResults.non_preprocessed,'前処理なし');
    selModal.style.display='block';
  };

  const applyResult = type=>{
    const r=aiResults[type];
    if(!r||r.status!=='success') return;
    materialType.value=r.material_type||'その他';
    materialType.dispatchEvent(new Event('change'));

    switch(r.material_type){
      case '木材':   $('wood_type').value=r.subtype||''; break;
      case 'ボード材':$('board_material_type').value=r.subtype||''; break;
      case 'パネル材':$('panel_type').value=r.subtype||''; break;
    }
    if(isNum(r.size_1)) $('material_size_1').value=r.size_1;
    if(isNum(r.size_2)) $('material_size_2').value=r.size_2;
    if(isNum(r.size_3)) $('material_size_3').value=r.size_3;
    if(isNum(r.quantity)) $('quantity').value=r.quantity;

    if(r.location){
      const p=parseJPAddr(r.location);
      if(p){
        mPrefInput.value=p.prefecture; refreshCities(p.prefecture);
        mCityInput.value=p.city; refreshAddr(p.prefecture,p.city);
        mAddrInput.value=p.address;
      }else{ mAddrInput.value=r.location; }
    }
    toggleSubtypes();
  };

  /* ─────────────── カメラ ─────────────── */

  const startCamera = async ()=>{
    try{
      stream = await navigator.mediaDevices.getUserMedia({video:true});
      cameraStream.srcObject=stream;
      captureBtn.disabled=false;
      cameraModal.style.display='block';
    }catch{ alert('カメラを使用できません'); }
  };

  const captureImg = ()=>{
    const canvas=document.createElement('canvas');
    canvas.width=cameraStream.videoWidth;
    canvas.height=cameraStream.videoHeight;
    canvas.getContext('2d').drawImage(cameraStream,0,0);
    canvas.toBlob(b=>{
      const f=new File([b],'capture.png',{type:'image/png'});
      const dt=new DataTransfer();dt.items.add(f);imageInput.files=dt.files;
      sendImg(f);
    },'image/png');
    cameraModal.style.display='none';
    stream.getTracks().forEach(t=>t.stop());
  };

  /* ─────────────── イベント登録 ─────────────── */

  const bindEvents = ()=>{
    materialType.addEventListener('change',toggleSubtypes);
    ['material_size_1','material_size_2','material_size_3','quantity']
      .forEach(id=>$(id).addEventListener('input',validateNumInput));

    imageInput.addEventListener('change',e=>{
      const f=e.target.files[0];
      if(!f) return;
      $('imagePreview').src=URL.createObjectURL(f);
      $('imagePreview').style.display='block';
      delImgBtn.style.display='inline-block';
      sendImg(f); logForm();
    });
    delImgBtn.addEventListener('click',()=>{
      imageInput.value='';$('imagePreview').style.display='none';delImgBtn.style.display='none';
    });

    startCamBtn.addEventListener('click',startCamera);
    captureBtn  .addEventListener('click',captureImg);
    closeCamBtn .addEventListener('click',()=>{cameraModal.style.display='none';if(stream)stream.getTracks().forEach(t=>t.stop());});

    mPrefInput.addEventListener('change',e=>{refreshCities(e.target.value);addrDL.innerHTML='';});
    mCityInput.addEventListener('input',e=>{refreshAddr(mPrefInput.value,e.target.value);});

    selContent.addEventListener('click',e=>{
      if(e.target.matches('.select-result-btn')){
        applyResult(e.target.dataset.type);
        selModal.style.display='none';
      }
    });
    closeSelBtn.addEventListener('click',()=>selModal.style.display='none');
    closeSucBtn.addEventListener('click',()=>successModal.style.display='none');

    window.addEventListener('click',e=>{
      if(e.target===cameraModal) cameraModal.style.display='none';
      if(e.target===selModal)    selModal.style.display='none';
    });
  };

  /* ─────────────── 初期化 ─────────────── */

  toggleSubtypes(); bindEvents(); logForm();

  if(document.querySelector('.flash-message.alert-success')){
    successModal.style.display='block';
    setTimeout(()=>location.href=dashboardURL,2000);
  }
});
