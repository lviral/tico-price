(function(){
  var t=localStorage.getItem("theme"),d=window.matchMedia("(prefers-color-scheme:dark)").matches;
  document.documentElement.setAttribute("data-theme",t||(d?"dark":"light"));
  document.addEventListener("DOMContentLoaded",function(){
    var btn=document.getElementById("theme-toggle");
    if(!btn)return;
    btn.textContent=document.documentElement.getAttribute("data-theme")==="dark"?"☀️":"🌙";
    btn.addEventListener("click",function(){
      var next=document.documentElement.getAttribute("data-theme")==="dark"?"light":"dark";
      localStorage.setItem("theme",next);
      document.documentElement.setAttribute("data-theme",next);
      btn.textContent=next==="dark"?"☀️":"🌙";
    });
  });
})();
